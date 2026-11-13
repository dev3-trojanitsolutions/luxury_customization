"""Multi-UOM (packing) on purchase item rows.

The "+ UOM" dialog stores a free list of UOMs on the row as JSON. Each UOM says what one unit of it
contains, in any other UOM of the list or the stock UOM, so packing need not be a single chain:

	{"stock_uom": "Nos", "levels": [
		{"uom": "Pallet", "inner": "Carton", "contains": 20, "qty": 0},
		{"uom": "Carton", "inner": "Box",    "contains": 10, "qty": 2, "rate": 900, "selling_price": 1200},
		{"uom": "Bag",    "inner": "Nos",    "contains": 50, "qty": 0},
		{"uom": "Box",    "inner": "Nos",    "contains": 24, "qty": 3, "rate": 100},
		{"uom": "Nos",    "qty": 0}]}

CF (stock units per unit) = contains x CF(inner), so Carton = 10 x 24 = 240 and Pallet = 20 x 240.
Rows saved by the earlier chain dialog (`per_parent`, top first) are converted on read.

The row is posted in the used UOM with the smallest CF when the total fits it in whole units, else
in the stock UOM. ERPNext then works out stock_qty = qty x conversion_factor, the stock ledger,
valuation and GL as usual.

`rate` (buying price, in the currency the row's price is entered in) and `selling_price` (company
currency) are optional per UOM. The row rate is the blended price: sum(qty x rate) / row qty.
On submit they are saved as Item Prices for that UOM.
"""

import json

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from frappe.utils import flt, now

ITEM_DOCTYPES = ["Purchase Order Item", "Purchase Receipt Item", "Purchase Invoice Item", "Supplier Quotation Item"]
FIELDS = [
	{
		"fieldname": "add_uom",
		"fieldtype": "Button",
		"label": "+ UOM",
		"insert_after": "uom",
		"in_list_view": 1,
		"columns": 1,
	},
	{
		"fieldname": "uom_hierarchy",
		"fieldtype": "JSON",
		"label": "UOM Hierarchy",
		"insert_after": "add_uom",
		"hidden": 1,
		"print_hide": 1,
		"report_hide": 1,
	},
]
FIELDNAMES = [f["fieldname"] for f in FIELDS]
CF_PRECISION = 9


def create_custom_fields():
	for doctype in ITEM_DOCTYPES:
		for field in FIELDS:
			if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field["fieldname"]}):
				create_custom_field(doctype, field)
		frappe.clear_cache(doctype=doctype)


def delete_custom_fields():
	for doctype in ITEM_DOCTYPES:
		for fieldname in FIELDNAMES:
			frappe.delete_doc("Custom Field", f"{doctype}-{fieldname}", ignore_missing=True)
		frappe.clear_cache(doctype=doctype)


# --- Calculation ---------------------------------------------------------------------------------


def parse(value):
	if not value:
		return None
	data = json.loads(value) if isinstance(value, str) else value
	return data if data and data.get("levels") else None


def normalize(levels):
	"""Convert the earlier chain format (top first, `per_parent`) to inner / contains, in place."""
	if any("inner" in level for level in levels) or not any("per_parent" in level for level in levels):
		return levels
	for level, below in zip(levels, levels[1:]):
		level["inner"], level["contains"] = below.get("uom"), flt(below.get("per_parent"))
	for level in levels:
		level.pop("per_parent", None)
	return levels


def conversion_factors(levels, stock_uom):
	"""CF to stock UOM per level, in list order. Validates names, inner UOMs, numbers and loops."""
	normalize(levels)
	by_uom = {}
	for level in levels:
		if not level.get("uom"):
			frappe.throw(_("Every line needs a UOM"))
		if level["uom"] in by_uom:
			frappe.throw(_("UOM {0} is used twice").format(level["uom"]))
		by_uom[level["uom"]] = level

	def factor(uom, path):
		if uom == stock_uom:
			return 1.0
		level = by_uom.get(uom)
		if not level:
			frappe.throw(_("{0} is not in the list").format(uom))
		if uom in path:
			frappe.throw(_("{0} contains itself").format(" > ".join([*path, uom])))
		if not level.get("inner"):
			frappe.throw(_("Say what 1 {0} contains").format(uom))
		if flt(level.get("contains")) <= 0:
			frappe.throw(_("Enter how many {0} are in 1 {1}").format(level["inner"], uom))
		return flt(level["contains"]) * factor(level["inner"], [*path, uom])

	factors = [flt(factor(level["uom"], []), CF_PRECISION) for level in levels]
	for level, cf in zip(levels, factors):
		if cf < 1:
			frappe.throw(_("{0} is smaller than the stock UOM {1}").format(level["uom"], stock_uom))
	return factors


def compute(hierarchy, stock_uom):
	"""(posting uom, conversion factor, qty, total stock qty), or None when no level has a quantity."""
	levels = hierarchy["levels"]
	factors = conversion_factors(levels, stock_uom)
	total = sum(flt(level.get("qty")) * cf for level, cf in zip(levels, factors))
	used = [(cf, level["uom"]) for level, cf in zip(levels, factors) if flt(level.get("qty")) > 0]
	if not used:
		return None
	cf, uom = min(used)
	if abs(total / cf - round(total / cf)) > 1e-9:
		cf, uom = 1.0, stock_uom  # e.g. 1 Bag (50) + 1 Box (24): 74 Nos is no whole number of Boxes
	return uom, cf, total / cf, total


# --- Transaction rows ----------------------------------------------------------------------------


def apply_to_items(doc, method=None):
	"""Keep each row's hierarchy in step with the row. The row's uom, qty and CF always win."""
	if doc.docstatus != 0:
		return
	for row in doc.get("items") or []:
		hierarchy = parse(row.get("uom_hierarchy"))
		if hierarchy and row.item_code:
			row.uom_hierarchy = sync_row(row, hierarchy, bool(doc.get("multi_currency_calculation")))
	sync_row_uoms_to_item(doc)


def sync_row(row, hierarchy, multi_currency=False):
	stock_uom = row.stock_uom or frappe.get_cached_value("Item", row.item_code, "stock_uom")
	if hierarchy.get("stock_uom") != stock_uom:
		return None  # item or stock UOM changed: the old hierarchy no longer applies
	levels = hierarchy["levels"]
	factors = conversion_factors(levels, stock_uom)
	result = compute(hierarchy, stock_uom)

	# Imports / API rows that only carry the hierarchy: post it on the row.
	if result and not flt(row.qty):
		row.uom, row.conversion_factor, row.qty = result[0], result[1], flt(result[2], row.precision("qty"))
		apply_prices(row, hierarchy, multi_currency, force=True)
		return json.dumps(hierarchy)

	if stock_uom not in [level["uom"] for level in levels]:
		levels.append({"uom": stock_uom, "qty": 0})
		factors.append(1.0)
	uoms = [level["uom"] for level in levels]
	if row.uom not in uoms:
		return None  # UOM changed outside the dialog
	cf = factors[uoms.index(row.uom)]
	if row.conversion_factor and abs(flt(row.conversion_factor) - cf) > 10**-CF_PRECISION * cf:
		return None  # conversion factor typed by hand
	row.conversion_factor = cf

	if result and result[0] == row.uom and abs(flt(result[2]) - flt(row.qty)) < 10**-6:
		apply_prices(row, hierarchy, multi_currency)
		return json.dumps(hierarchy)
	# qty edited (e.g. a partial receipt of a mapped row): keep the levels, move the row's qty onto its UOM.
	# The row's rate is left alone, so a PR / PI keeps the rate of the PO it was made from.
	for level in levels:
		level["qty"] = flt(row.qty) if level["uom"] == row.uom else 0
	return json.dumps(hierarchy)


# --- Prices ------------------------------------------------------------------------------------


def blended_rate(hierarchy, qty):
	"""Sum(qty x rate) / qty, or None when a level with a quantity has no buying price."""
	used = [level for level in hierarchy["levels"] if flt(level.get("qty")) > 0]
	if not used or not flt(qty) or any(flt(level.get("rate")) <= 0 for level in used):
		return None
	return sum(flt(level["qty"]) * flt(level["rate"]) for level in used) / flt(qty)


def apply_prices(row, hierarchy, multi_currency=False, force=False):
	"""Set the row price from the level prices. A price typed on the row by hand drops the level prices."""
	rate = blended_rate(hierarchy, row.qty)
	if rate is None:
		return
	precision = row.precision("rate")
	field = "other_currency_rate" if multi_currency else "rate"
	if not force and flt(row.get(field)) and flt(row.get(field), precision) != flt(rate, precision):
		for level in hierarchy["levels"]:
			level.pop("rate", None)
		return
	if field == "rate":
		row.price_list_rate = row.rate = flt(rate, precision)
		row.discount_percentage = row.discount_amount = row.margin_rate_or_amount = 0
	else:
		row.other_currency_rate = flt(rate, precision)
	posting = next((level for level in hierarchy["levels"] if level["uom"] == row.uom), None)
	if posting and flt(posting.get("selling_price")) > 0 and row.meta.has_field("selling_price"):
		row.selling_price = flt(posting["selling_price"])


def price_currency(doc):
	"""Currency the row's buying price is entered in."""
	return doc.get("calculation_currency") if doc.get("multi_currency_calculation") else doc.get("currency")


def find_item_price(item_code, price_list, uom, stock_uom):
	"""Plain list price for exactly this UOM; for the stock UOM also one without a UOM."""
	base = {"item_code": item_code, "price_list": price_list, "customer": ("is", "not set"),
		"supplier": ("is", "not set"), "batch_no": ("is", "not set")}
	for uom_filter in [uom] + ([("is", "not set")] if uom == stock_uom else []):
		price = frappe.db.get_value(
			"Item Price", {**base, "uom": uom_filter}, ["name", "price_list_rate"], as_dict=True, order_by="valid_from desc"
		)
		if price:
			return price


def item_prices(item_code, price_list, currency=None):
	"""{uom: price} from the price list, or {} when the list's currency is not `currency`."""
	if not (item_code and price_list):
		return {}
	if currency and frappe.get_cached_value("Price List", price_list, "currency") != currency:
		return {}
	stock_uom = frappe.get_cached_value("Item", item_code, "stock_uom")
	result = {}
	for uom in [stock_uom, *item_uoms(item_code)]:
		price = find_item_price(item_code, price_list, uom, stock_uom)
		if price:
			result[uom] = flt(price.price_list_rate)
	return result


def save_item_price(item_code, price_list, uom, stock_uom, rate):
	price = find_item_price(item_code, price_list, uom, stock_uom)
	if price:
		if flt(price.price_list_rate) == flt(rate):
			return
		item_price = frappe.get_doc("Item Price", price.name)
		item_price.price_list_rate = rate
	else:
		item_price = frappe.get_doc({
			"doctype": "Item Price",
			"item_code": item_code,
			"price_list": price_list,
			"uom": uom,
			"price_list_rate": rate,
		})
	item_price.flags.ignore_permissions = True
	item_price.save()


def on_submit(doc, method=None):
	"""Save every level's buying and selling price as an Item Price for that UOM."""
	buying_list = doc.get("buying_price_list")
	buying_ok = buying_list and frappe.get_cached_value("Price List", buying_list, "currency") == price_currency(doc)
	company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	skipped = False
	for row in doc.get("items") or []:
		hierarchy = parse(row.get("uom_hierarchy"))
		if not (hierarchy and row.item_code):
			continue
		# Item Price needs the UOM on the Item (before_validate normally added it already).
		factors = conversion_factors(hierarchy["levels"], row.stock_uom)
		add_item_uoms(row.item_code, {level["uom"]: cf for level, cf in zip(hierarchy["levels"], factors)})
		sell_list = row.get("sell_price_list")
		sell_ok = sell_list and frappe.get_cached_value("Price List", sell_list, "currency") == company_currency
		for level in hierarchy["levels"]:
			if flt(level.get("rate")) > 0:
				if buying_ok:
					save_item_price(row.item_code, buying_list, level["uom"], row.stock_uom, flt(level["rate"]))
				else:
					skipped = True
			# The row's own Selling Price is saved by selling_price.on_submit.
			own = level["uom"] == row.uom and flt(row.get("selling_price")) > 0
			if flt(level.get("selling_price")) > 0 and sell_ok and not own:
				save_item_price(row.item_code, sell_list, level["uom"], row.stock_uom, flt(level["selling_price"]))
	if skipped:
		frappe.msgprint(
			_("UOM buying prices were not saved: Price List {0} is not in {1}").format(buying_list or "-", price_currency(doc)),
			alert=True, indicator="orange",
		)


# --- Item master ---------------------------------------------------------------------------------


def item_uoms(item_code):
	"""{uom: (UOM Conversion Detail name or None, CF)} for the item, falling back to its template."""
	variant_of = frappe.get_cached_value("Item", item_code, "variant_of")
	result = {}
	for code in filter(None, [variant_of, item_code]):  # the item's own rows override the template's
		for d in frappe.get_all(
			"UOM Conversion Detail",
			filters={"parent": code, "parenttype": "Item"},
			fields=["name", "uom", "conversion_factor"],
		):
			result[d.uom] = (d.name if code == item_code else None, flt(d.conversion_factor))
	return result


@frappe.whitelist()
def get_item_uom_info(item_code, buying_price_list=None, buying_currency=None, sell_price_list=None, company=None):
	item = frappe.get_cached_value("Item", item_code, ["stock_uom", "purchase_uom"], as_dict=True)
	if not item:
		return {}
	uoms = [{"uom": uom, "conversion_factor": cf} for uom, (_name, cf) in item_uoms(item_code).items()]
	company_currency = company and frappe.get_cached_value("Company", company, "default_currency")
	return {
		"stock_uom": item.stock_uom,
		"purchase_uom": item.purchase_uom,
		"uoms": uoms,
		"buying_prices": item_prices(item_code, buying_price_list, buying_currency),
		"selling_prices": item_prices(item_code, sell_price_list, company_currency) if company_currency else {},
	}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def uom_query(doctype, txt, searchfield, start, page_len, filters):
	"""UOM search for the dialog: the item's own UOMs first, and UOMs already in the chain left out."""
	item_code = filters.get("item_code")
	exclude = filters.get("exclude") or []
	own = set(item_uoms(item_code)) | {frappe.get_cached_value("Item", item_code, "stock_uom")} if item_code else set()
	conditions = [["enabled", "=", 1], ["name", "like", f"%{txt}%"]]
	if exclude:
		conditions.append(["name", "not in", exclude])
	names = frappe.get_all("UOM", filters=conditions, pluck="name", order_by="name", limit=500)
	names.sort(key=lambda n: (n not in own, n))
	return [[n] for n in names[start : start + page_len]]


def insert_item_uom(item_code, uom, cf):
	# Insert the child row directly: saving the whole Item would run unrelated Item validations
	# in the middle of a purchase transaction.
	idx = frappe.db.count("UOM Conversion Detail", {"parent": item_code, "parenttype": "Item"}) + 1
	frappe.get_doc({
		"doctype": "UOM Conversion Detail",
		"parent": item_code,
		"parenttype": "Item",
		"parentfield": "uoms",
		"idx": idx,
		"uom": uom,
		"conversion_factor": cf,
	}).db_insert()

def add_item_uoms(item_code, conversions, update=()):
	"""Add missing {uom: cf} rows to the Item; change existing ones only when listed in `update`."""
	stock_uom = frappe.get_cached_value("Item", item_code, "stock_uom")
	existing = item_uoms(item_code)
	changed = False
	for uom, cf in conversions.items():
		cf = flt(cf, CF_PRECISION)
		if not uom or uom == stock_uom or cf <= 0:
			continue
		name, old_cf = existing.get(uom, (None, None))
		if old_cf is None:
			insert_item_uom(item_code, uom, cf)
			changed = True
		elif uom in update and abs(old_cf - cf) > 10**-CF_PRECISION:
			if name:
				frappe.db.set_value("UOM Conversion Detail", name, "conversion_factor", cf, update_modified=False)
			else:  # only the template has it: give the variant its own row
				insert_item_uom(item_code, uom, cf)
			changed = True
	if changed:
		# Bump modified so an Item form left open must reload instead of saving over the new rows.
		frappe.db.set_value("Item", item_code, "modified", now(), update_modified=False)
		frappe.clear_document_cache("Item", item_code)
	return changed


@frappe.whitelist()
def save_item_uoms(item_code, levels, update=None):
	levels = json.loads(levels) if isinstance(levels, str) else levels
	update = json.loads(update) if isinstance(update, str) else (update or [])
	if not frappe.has_permission("Item", "write", doc=item_code):
		return {"saved": False, "reason": "permission"}
	stock_uom = frappe.get_cached_value("Item", item_code, "stock_uom")
	factors = conversion_factors(levels, stock_uom)
	add_item_uoms(item_code, {level["uom"]: cf for level, cf in zip(levels, factors)}, update)
	return {"saved": True}


def sync_row_uoms_to_item(doc):
	"""Any UOM picked on a row (dialog or standard UOM column) is added to the Item with its CF."""
	pending = {}
	for row in doc.get("items") or []:
		if not (row.item_code and row.stock_uom):
			continue
		conversions = pending.setdefault(row.item_code, {})
		hierarchy = parse(row.get("uom_hierarchy"))
		if hierarchy:  # every level, not only the posted one
			for level, cf in zip(hierarchy["levels"], conversion_factors(hierarchy["levels"], row.stock_uom)):
				conversions.setdefault(level["uom"], cf)
		if row.uom and row.uom != row.stock_uom and flt(row.conversion_factor) > 0:
			conversions.setdefault(row.uom, flt(row.conversion_factor))
	skipped = []
	for item_code, conversions in pending.items():
		existing = item_uoms(item_code)
		missing = {uom: cf for uom, cf in conversions.items() if uom not in existing}
		if not missing:
			continue
		if not frappe.has_permission("Item", "write", doc=item_code):
			skipped.append(item_code)
			continue
		add_item_uoms(item_code, missing)
	if skipped:
		frappe.msgprint(
			_("UOMs not saved to Item {0}: no permission").format(", ".join(skipped)), alert=True, indicator="orange"
		)
