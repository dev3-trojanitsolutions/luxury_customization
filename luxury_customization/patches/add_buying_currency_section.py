import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

DOCTYPES = ["Supplier Quotation", "Purchase Order", "Purchase Receipt", "Purchase Invoice"]


def execute():
	for doctype in DOCTYPES:
		if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": "multi_currency_calculation"}):
			continue

		# New section right after the standard Currency and Price List section
		if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": "buying_currency"}):
			create_custom_field(
				doctype,
				{
					"fieldname": "buying_currency",
					"fieldtype": "Section Break",
					"label": "Buying Currency",
					"insert_after": "ignore_pricing_rule",
				},
			)

		# calculation_currency and calculation_exchange_rate are chained after multi_currency_calculation
		set_insert_after(doctype, "multi_currency_calculation", "buying_currency")
		# The totals column was chained after calculation_exchange_rate; keep it in its own section
		set_insert_after(doctype, "additional_currency_column", "additional_currency_section")

		frappe.clear_cache(doctype=doctype)


def set_insert_after(doctype, fieldname, insert_after):
	filters = {"dt": doctype, "fieldname": fieldname}
	if frappe.db.exists("Custom Field", filters):
		frappe.db.set_value("Custom Field", filters, "insert_after", insert_after)
