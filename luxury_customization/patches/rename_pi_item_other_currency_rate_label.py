import frappe


def execute():
	filters = {"dt": "Purchase Invoice Item", "fieldname": "other_currency_rate"}
	if frappe.db.exists("Custom Field", filters):
		frappe.db.set_value("Custom Field", filters, "label", "Buying Rate")
		frappe.clear_cache(doctype="Purchase Invoice Item")
