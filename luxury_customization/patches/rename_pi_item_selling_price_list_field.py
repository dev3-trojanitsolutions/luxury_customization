import frappe


def execute():
	# Row field "selling_price_list" makes ERPNext's _apply_price_list read self.customer on Purchase Invoice.
	# Drop it; after_migrate creates "sell_price_list" in its place.
	name = "Purchase Invoice Item-selling_price_list"
	if frappe.db.exists("Custom Field", name):
		frappe.delete_doc("Custom Field", name, ignore_missing=True)
	frappe.db.set_value(
		"Custom Field", {"dt": "Purchase Invoice Item", "fieldname": "previous_selling_price"},
		"insert_after", "sell_price_list",
	)
	frappe.clear_cache(doctype="Purchase Invoice Item")
