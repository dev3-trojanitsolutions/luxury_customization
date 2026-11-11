import frappe

DOCTYPES = ["Supplier Quotation", "Purchase Order", "Purchase Receipt", "Purchase Invoice"]


def execute():
	for doctype in DOCTYPES:
		filters = {"dt": doctype, "fieldname": "additional_net_total"}
		if frappe.db.exists("Custom Field", filters):
			frappe.db.set_value("Custom Field", filters, "hidden", 1)
			frappe.clear_cache(doctype=doctype)
