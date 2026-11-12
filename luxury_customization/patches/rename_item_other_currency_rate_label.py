import frappe

ITEM_DOCTYPES = ["Supplier Quotation Item", "Purchase Order Item", "Purchase Receipt Item", "Purchase Invoice Item"]


def execute():
	for doctype in ITEM_DOCTYPES:
		filters = {"dt": doctype, "fieldname": "other_currency_rate"}
		if frappe.db.exists("Custom Field", filters):
			frappe.db.set_value("Custom Field", filters, "label", "Buying Rate")
			frappe.clear_cache(doctype=doctype)
