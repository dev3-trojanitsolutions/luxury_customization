import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from luxury_customization.customizations.uom_hierarchy import (
	blended_rate,
	compute,
	find_item_price,
	item_uoms,
	on_submit,
	save_item_uoms,
	sync_row,
	sync_row_uoms_to_item,
)

TEST_ITEM = "_Test UOM Hierarchy Pen"


def pen_levels(carton=0, box=0, packet=0, nos=0):
	return [
		{"uom": "Carton", "per_parent": 0, "qty": carton},
		{"uom": "Box", "per_parent": 10, "qty": box},
		{"uom": "Packet", "per_parent": 5, "qty": packet},
		{"uom": "Nos", "per_parent": 5, "qty": nos},
	]


def hierarchy(**qty):
	return {"stock_uom": "Nos", "levels": pen_levels(**qty)}


class TestUOMHierarchyCalculation(IntegrationTestCase):
	def test_single_level(self):
		# 2 Cartons x 10 x 5 x 5 = 500 Nos, posted as 2 Carton with CF 250
		self.assertEqual(compute(hierarchy(carton=2), "Nos"), ("Carton", 250, 2, 500))

	def test_mixed_levels_post_in_smallest_used_level(self):
		uom, cf, qty, total = compute(hierarchy(carton=2, box=3, packet=1), "Nos")
		self.assertEqual((uom, cf, qty, total), ("Packet", 5, 116, 580))

	def test_decimal_quantity(self):
		self.assertEqual(compute(hierarchy(carton=1.5), "Nos")[3], 375)

	def test_stock_uom_packet(self):
		data = {"stock_uom": "Packet", "levels": pen_levels(carton=2)[:3]}
		self.assertEqual(compute(data, "Packet"), ("Carton", 50, 2, 100))

	def test_no_quantity(self):
		self.assertIsNone(compute(hierarchy(), "Nos"))

	def test_invalid_hierarchies(self):
		zero = hierarchy(carton=1)
		zero["levels"][1]["per_parent"] = 0
		smaller = {"stock_uom": "Packet", "levels": [{"uom": "Packet", "qty": 1}, {"uom": "Nos", "per_parent": 0.2}]}
		duplicate = hierarchy(carton=1)
		duplicate["levels"][1]["uom"] = "Carton"
		wrong_last = {"stock_uom": "Nos", "levels": pen_levels(carton=1)[:3]}
		for data, stock_uom in ((zero, "Nos"), (smaller, "Packet"), (duplicate, "Nos"), (wrong_last, "Nos")):
			with self.assertRaises(frappe.ValidationError):
				compute(data, stock_uom)


def free_list(**qty):
	"""Not a chain: Pallet > Carton > Box > Nos, and Bag straight to Nos."""
	return {"stock_uom": "Nos", "levels": [
		{"uom": "Pallet", "inner": "Carton", "contains": 20, "qty": qty.get("pallet", 0)},
		{"uom": "Carton", "inner": "Box", "contains": 10, "qty": qty.get("carton", 0)},
		{"uom": "Bag", "inner": "Nos", "contains": 50, "qty": qty.get("bag", 0)},
		{"uom": "Box", "inner": "Nos", "contains": 24, "qty": qty.get("box", 0)},
		{"uom": "Nos", "qty": qty.get("nos", 0)},
	]}


class TestUOMFreeList(IntegrationTestCase):
	def test_factors_follow_each_inner_uom(self):
		from luxury_customization.customizations.uom_hierarchy import conversion_factors

		self.assertEqual(conversion_factors(free_list()["levels"], "Nos"), [4800, 240, 50, 24, 1])

	def test_mixed_uoms_post_in_smallest_that_fits(self):
		# 2 Carton (480) + 3 Box (72) = 552 Nos = 23 Box
		self.assertEqual(compute(free_list(carton=2, box=3), "Nos"), ("Box", 24, 23, 552))

	def test_uneven_mix_posts_in_stock_uom(self):
		# 1 Bag (50) + 1 Box (24) = 74 Nos: not a whole number of Boxes
		self.assertEqual(compute(free_list(bag=1, box=1), "Nos"), ("Nos", 1, 74, 74))

	def test_loop_and_unknown_inner_are_rejected(self):
		loop = {"stock_uom": "Nos", "levels": [
			{"uom": "Carton", "inner": "Box", "contains": 2, "qty": 1},
			{"uom": "Box", "inner": "Carton", "contains": 2},
			{"uom": "Nos"}]}
		unknown = {"stock_uom": "Nos", "levels": [{"uom": "Carton", "inner": "Packet", "contains": 2, "qty": 1}, {"uom": "Nos"}]}
		for data in (loop, unknown):
			with self.assertRaises(frappe.ValidationError):
				compute(data, "Nos")

	def test_old_chain_rows_still_work(self):
		data = hierarchy(carton=2)
		self.assertEqual(compute(data, "Nos"), ("Carton", 250, 2, 500))
		self.assertEqual(data["levels"][0], {"uom": "Carton", "qty": 2, "inner": "Box", "contains": 10})


class TestUOMHierarchyRowSync(IntegrationTestCase):
	def row(self, **values):
		row = frappe.new_doc("Purchase Receipt Item")
		row.update({"item_code": TEST_ITEM, "stock_uom": "Nos", **values})
		return row

	def setUp(self):
		make_test_item()

	def test_row_matching_hierarchy_is_kept(self):
		row = self.row(uom="Carton", qty=2, conversion_factor=250)
		self.assertEqual(json.loads(sync_row(row, hierarchy(carton=2)))["levels"][0]["qty"], 2)
		self.assertEqual(row.conversion_factor, 250)

	def test_partial_receipt_moves_qty_to_row_uom(self):
		row = self.row(uom="Carton", qty=1, conversion_factor=250)
		levels = json.loads(sync_row(row, hierarchy(carton=2, box=3)))["levels"]
		self.assertEqual([level["qty"] for level in levels], [1, 0, 0, 0])

	def test_manual_conversion_factor_clears_hierarchy(self):
		row = self.row(uom="Carton", qty=2, conversion_factor=200)
		self.assertIsNone(sync_row(row, hierarchy(carton=2)))
		self.assertEqual(row.conversion_factor, 200)

	def test_import_with_only_hierarchy_posts_row(self):
		row = self.row(uom="Nos", qty=0, conversion_factor=1)
		sync_row(row, hierarchy(carton=2, box=3))
		self.assertEqual((row.uom, row.conversion_factor, row.qty), ("Box", 25, 23))


class TestUOMHierarchyItemMaster(IntegrationTestCase):
	def setUp(self):
		make_test_item()

	def test_levels_saved_to_item(self):
		save_item_uoms(TEST_ITEM, pen_levels(carton=2))
		uoms = {uom: cf for uom, (_name, cf) in item_uoms(TEST_ITEM).items()}
		self.assertEqual((uoms["Carton"], uoms["Box"], uoms["Packet"]), (250, 25, 5))

	def test_existing_factor_changes_only_when_confirmed(self):
		save_item_uoms(TEST_ITEM, pen_levels(carton=2))
		changed = pen_levels(carton=2)
		changed[1]["per_parent"] = 8  # 1 Carton = 8 Box -> CF 200
		save_item_uoms(TEST_ITEM, changed)
		self.assertEqual(item_uoms(TEST_ITEM)["Carton"][1], 250)
		save_item_uoms(TEST_ITEM, changed, update=["Carton"])
		self.assertEqual(item_uoms(TEST_ITEM)["Carton"][1], 200)

	def test_standard_uom_column_is_saved_to_item(self):
		doc = frappe._dict(items=[frappe._dict(item_code=TEST_ITEM, uom="Box", stock_uom="Nos", conversion_factor=25)])
		sync_row_uoms_to_item(doc)
		self.assertEqual(item_uoms(TEST_ITEM)["Box"][1], 25)


def priced(**qty):
	data = hierarchy(**qty)
	data["levels"][0].update(rate=900, selling_price=1200)
	data["levels"][1].update(rate=100, selling_price=130)
	return data


class TestUOMHierarchyPrices(IntegrationTestCase):
	def setUp(self):
		make_test_item()

	def row(self, **values):
		row = frappe.new_doc("Purchase Receipt Item")
		row.update({"item_code": TEST_ITEM, "stock_uom": "Nos", **values})
		return row

	def test_blended_rate(self):
		# 2 Carton @ 900 + 3 Box @ 100 = 2,100 over 23 Box
		self.assertAlmostEqual(blended_rate(priced(carton=2, box=3), 23), 2100 / 23)

	def test_blended_rate_needs_a_price_on_every_used_level(self):
		self.assertIsNone(blended_rate(priced(carton=2, packet=1), 116))

	def test_row_gets_blended_rate(self):
		row = self.row(uom="Box", qty=23, conversion_factor=25, rate=0)
		sync_row(row, priced(carton=2, box=3))
		self.assertEqual(row.rate, flt(2100 / 23, row.precision("rate")))
		self.assertEqual(row.price_list_rate, row.rate)
		self.assertAlmostEqual(row.qty * row.rate, 2100, delta=0.01)

	def test_single_level_gives_clean_rate(self):
		row = self.row(uom="Carton", qty=2, conversion_factor=250, rate=0)
		sync_row(row, priced(carton=2))
		self.assertEqual(row.rate, 900)

	def test_multi_currency_sets_buying_rate(self):
		row = self.row(uom="Carton", qty=2, conversion_factor=250, other_currency_rate=0)
		sync_row(row, priced(carton=2), multi_currency=True)
		self.assertEqual(row.other_currency_rate, 900)

	def test_hand_typed_rate_drops_level_prices(self):
		row = self.row(uom="Carton", qty=2, conversion_factor=250, rate=850)
		levels = json.loads(sync_row(row, priced(carton=2)))["levels"]
		self.assertEqual(row.rate, 850)
		self.assertNotIn("rate", levels[0])

	def test_partial_receipt_keeps_rate(self):
		row = self.row(uom="Carton", qty=1, conversion_factor=250, rate=777)
		sync_row(row, priced(carton=2))
		self.assertEqual(row.rate, 777)

	def test_on_submit_saves_item_price_per_uom(self):
		buying = frappe.db.get_value("Price List", {"buying": 1, "enabled": 1}, ["name", "currency"], as_dict=True)
		selling = frappe.db.get_value(
			"Price List", {"selling": 1, "enabled": 1, "currency": buying.currency}, "name"
		)
		company = frappe.db.get_value("Company", {"default_currency": buying.currency}, "name")
		if not (buying and selling and company):
			self.skipTest("needs a buying and a selling price list in a company's currency")
		row = frappe._dict(
			item_code=TEST_ITEM, stock_uom="Nos", uom="Carton", selling_price=0, sell_price_list=selling,
			uom_hierarchy=json.dumps(priced(carton=2, box=3)),
		)
		doc = frappe._dict(items=[row], buying_price_list=buying.name, currency=buying.currency, company=company)
		on_submit(doc)
		self.assertEqual(find_item_price(TEST_ITEM, buying.name, "Carton", "Nos").price_list_rate, 900)
		self.assertEqual(find_item_price(TEST_ITEM, buying.name, "Box", "Nos").price_list_rate, 100)
		self.assertEqual(find_item_price(TEST_ITEM, selling, "Box", "Nos").price_list_rate, 130)

		# A changed price updates the same Item Price; a mismatched currency saves no buying price.
		changed = priced(carton=2)
		changed["levels"][0]["rate"] = 950
		row.uom_hierarchy = json.dumps(changed)
		on_submit(doc)
		self.assertEqual(find_item_price(TEST_ITEM, buying.name, "Carton", "Nos").price_list_rate, 950)
		changed["levels"][0]["rate"] = 990
		row.uom_hierarchy = json.dumps(changed)
		on_submit(frappe._dict(doc, currency="XXX"))
		self.assertEqual(find_item_price(TEST_ITEM, buying.name, "Carton", "Nos").price_list_rate, 950)


def make_test_item():
	for uom in ("Carton", "Box", "Packet", "Nos"):
		if not frappe.db.exists("UOM", uom):
			frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert(ignore_permissions=True)
	if frappe.db.exists("Item", TEST_ITEM):
		frappe.db.delete("UOM Conversion Detail", {"parent": TEST_ITEM, "uom": ("!=", "Nos")})
		return
	frappe.get_doc({
		"doctype": "Item",
		"item_code": TEST_ITEM,
		"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
		"stock_uom": "Nos",
		"is_stock_item": 1,
	}).insert(ignore_permissions=True)
