import frappe

DOCTYPES = ["Supplier Quotation", "Purchase Order", "Purchase Receipt", "Purchase Invoice"]


def execute():
	# The draft's consent dialog still sets the value; only the checkbox is hidden.
	for doctype in DOCTYPES:
		filters = {"dt": doctype, "fieldname": "multi_currency_calculation"}
		if frappe.db.exists("Custom Field", filters):
			frappe.db.set_value("Custom Field", filters, "hidden", 1)
			frappe.clear_cache(doctype=doctype)
