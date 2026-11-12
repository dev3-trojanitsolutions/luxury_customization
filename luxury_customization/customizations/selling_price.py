import frappe
from frappe.utils import flt

# Item row fields shared by Purchase Order, Purchase Receipt and Purchase Invoice.
SELLING_PRICE_FIELDS = [
    {
        "fieldname": "sell_price_list",
        "fieldtype": "Link",
        "label": "Selling Price List",
        "options": "Price List",
        "insert_after": "other_currency_rate",
    },
    {
        "fieldname": "previous_selling_price",
        "fieldtype": "Currency",
        "label": "Previous Selling Price",
        "options": "Company:company:default_currency",
        "read_only": 1,
        "in_list_view": 1,
        "insert_after": "sell_price_list",
    },
    {
        "fieldname": "selling_price",
        "fieldtype": "Currency",
        "label": "Selling Price",
        "options": "Company:company:default_currency",
        "in_list_view": 1,
        "insert_after": "previous_selling_price",
        "description": "New selling price; saved to Item Price on submit",
    },
]
SELLING_PRICE_FIELDNAMES = [f["fieldname"] for f in SELLING_PRICE_FIELDS]

def item_price_name(item_code, price_list, uom=None):
    # Plain list price (no customer/supplier/batch): same UOM first, then one without UOM.
    base = {"item_code": item_code, "price_list": price_list, "customer": ("is", "not set"),
            "supplier": ("is", "not set"), "batch_no": ("is", "not set")}
    uom = uom or frappe.db.get_value("Item", item_code, "stock_uom")  # rows get their UOM later in validate
    for uom_filter in ([uom] if uom else []) + [("is", "not set")]:
        name = frappe.db.get_value("Item Price", {**base, "uom": uom_filter}, "name", order_by="valid_from desc")
        if name:
            return name

@frappe.whitelist()
def get_selling_price(item_code, price_list, uom=None):
    if not (item_code and price_list):
        return 0
    name = item_price_name(item_code, price_list, uom)
    return flt(frappe.db.get_value("Item Price", name, "price_list_rate")) if name else 0

def set_selling_prices(doc):
    # Previous Selling Price shows the current Item Price; Selling Price stays whatever the user typed.
    if doc.docstatus != 0:
        return
    default_list = frappe.db.get_single_value("Selling Settings", "selling_price_list")
    for row in doc.items:
        if not row.get("sell_price_list"):
            row.sell_price_list = default_list
        row.previous_selling_price = get_selling_price(row.item_code, row.sell_price_list, row.uom)

def on_submit(doc, method=None):
    # Save each entered Selling Price to its Item Price (update the existing one or create it).
    for row in doc.items:
        price = flt(row.get("selling_price"))
        if price <= 0 or not (row.item_code and row.get("sell_price_list")):
            continue
        name = item_price_name(row.item_code, row.sell_price_list, row.uom)
        if name:
            item_price = frappe.get_doc("Item Price", name)
            if flt(item_price.price_list_rate) == price:
                continue
            item_price.price_list_rate = price
        else:
            item_price = frappe.get_doc({
                "doctype": "Item Price",
                "item_code": row.item_code,
                "price_list": row.sell_price_list,
                "uom": row.uom,
                "price_list_rate": price,
            })
        item_price.flags.ignore_permissions = True
        item_price.save()
