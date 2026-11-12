import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

ITEM_DOCTYPES = ["Supplier Quotation Item", "Purchase Order Item", "Purchase Receipt Item", "Purchase Invoice Item"]


def execute():
	# Rate comes from Buying Rate when Multi-Currency Calculation is on, so lock it in every row.
	for doctype in ITEM_DOCTYPES:
		make_property_setter(
			doctype, "rate", "read_only_depends_on", "eval:parent.multi_currency_calculation", "Code",
			validate_fields_for_doctype=False,
		)
		frappe.clear_cache(doctype=doctype)
