import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

DOCTYPES = ["Supplier Quotation", "Purchase Order", "Purchase Receipt", "Purchase Invoice"]

CUSTOM_FIELD_LABELS = {
	"calculation_currency": "Buying Currency",
	"calculation_exchange_rate": "Buying Currency Exchange Rate",
}

# Standard ERPNext fields: relabel with Property Setters, the ERPNext JSON stays unchanged
STANDARD_FIELD_LABELS = {
	"currency": "Payment Currency",
	"currency_and_price_list": "Payment Currency",
}


def execute():
	for doctype in DOCTYPES:
		for fieldname, label in CUSTOM_FIELD_LABELS.items():
			set_custom_field(doctype, fieldname, "label", label)

		for doctype_or_child in (doctype, f"{doctype} Item"):
			for name, description in frappe.get_all(
				"Custom Field",
				filters={"dt": doctype_or_child, "description": ["like", "%Calculation Currency%"]},
				fields=["name", "description"],
				as_list=True,
			):
				new = description.replace("Calculation Currency", "Buying Currency")
				frappe.db.set_value("Custom Field", name, "description", new)
			frappe.clear_cache(doctype=doctype_or_child)

		for fieldname, label in STANDARD_FIELD_LABELS.items():
			make_property_setter(doctype, fieldname, "label", label, "Data", validate_fields_for_doctype=False)

		frappe.clear_cache(doctype=doctype)


def set_custom_field(doctype, fieldname, prop, value):
	filters = {"dt": doctype, "fieldname": fieldname}
	if frappe.db.exists("Custom Field", filters):
		frappe.db.set_value("Custom Field", filters, prop, value)
