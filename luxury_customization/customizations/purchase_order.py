import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from frappe.utils import flt

# Display-only: reads the standard base_* (company currency) totals and never writes to them.
CONVERTED_TOTALS = {
    "additional_net_total": "base_net_total",
    "additional_total": "base_total",
    "additional_grand_total": "base_grand_total",
}
INPUT_FIELDS = ["multi_currency_calculation", "calculation_currency", "calculation_exchange_rate"]

def create_custom_fields():
    custom_fields = {
        "Purchase Order": [
            {
                "fieldname": "additional_currency_section",
                "fieldtype": "Section Break",
                "label": "Additional Currency Calculation",
                "insert_after": "rounded_total",
            },
            {
                "fieldname": "multi_currency_calculation",
                "fieldtype": "Check",
                "label": "Multi-Currency Calculation",
                "allow_on_submit": 1,
                "default": "0",
                "insert_after": "additional_currency_section",
            },
            {
                "fieldname": "calculation_currency",
                "fieldtype": "Link",
                "label": "Calculation Currency",
                "allow_on_submit": 1,
                "options": "Currency",
                "insert_after": "multi_currency_calculation",
                "depends_on": "eval:doc.multi_currency_calculation",
                "mandatory_depends_on": "eval:doc.multi_currency_calculation",
            },
            {
                "fieldname": "calculation_exchange_rate",
                "fieldtype": "Float",
                "label": "Calculation Exchange Rate",
                "allow_on_submit": 1,
                "precision": "9",
                "insert_after": "calculation_currency",
                "depends_on": "eval:doc.multi_currency_calculation",
                "mandatory_depends_on": "eval:doc.multi_currency_calculation",
                "description": "Calculation Currency per 1 unit of company currency",
            },
            {
                "fieldname": "additional_currency_column",
                "fieldtype": "Column Break",
                "insert_after": "calculation_exchange_rate",
            },
            {
                "fieldname": "additional_net_total",
                "fieldtype": "Currency",
                "label": "Additional Currency Net Total",
                "options": "calculation_currency",
                "read_only": 1,
                "allow_on_submit": 1,
                "insert_after": "additional_currency_column",
                "depends_on": "eval:doc.multi_currency_calculation",
            },
            {
                "fieldname": "additional_total",
                "fieldtype": "Currency",
                "label": "Additional Currency Total",
                "options": "calculation_currency",
                "read_only": 1,
                "allow_on_submit": 1,
                "insert_after": "additional_net_total",
                "depends_on": "eval:doc.multi_currency_calculation",
            },
            {
                "fieldname": "additional_grand_total",
                "fieldtype": "Currency",
                "label": "Additional Currency Grand Total",
                "options": "calculation_currency",
                "read_only": 1,
                "allow_on_submit": 1,
                "insert_after": "additional_total",
                "depends_on": "eval:doc.multi_currency_calculation",
            },
        ]
    }

    for doctype, fields in custom_fields.items():
        for field in fields:
            if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field["fieldname"]}):
                create_custom_field(doctype, field)
                frappe.db.commit()
                frappe.clear_cache(doctype=doctype)

def delete_custom_fields():
    custom_fields_to_delete = {
        "Purchase Order": [
            "additional_currency_section", "multi_currency_calculation", "calculation_currency",
            "calculation_exchange_rate", "additional_currency_column", "additional_net_total",
            "additional_total", "additional_grand_total",
        ]
    }

    for doctype, fields in custom_fields_to_delete.items():
        for field_name in fields:
            if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field_name}):
                frappe.delete_doc("Custom Field", f"{doctype}-{field_name}", ignore_missing=True)
                frappe.db.commit()
                frappe.clear_cache(doctype=doctype)

def copy_from_source(doc):
    # Mapped docs (get_mapped_doc) only carry mapped fields, so pick the settings up from the source.
    if not doc.is_new() or doc.multi_currency_calculation:
        return
    source_name = next((d.get("supplier_quotation") for d in doc.items if d.get("supplier_quotation")), None)
    if not source_name:
        return
    source = frappe.db.get_value("Supplier Quotation", source_name, INPUT_FIELDS, as_dict=True)
    if source and source.multi_currency_calculation:
        doc.update(source)

def validate(doc, method=None):
    copy_from_source(doc)
    if not doc.multi_currency_calculation:
        for target in CONVERTED_TOTALS:
            doc.set(target, 0)
        return

    if not doc.calculation_currency:
        frappe.throw(_("Please select a Calculation Currency"))

    rate = flt(doc.calculation_exchange_rate)
    if rate <= 0:
        frappe.throw(_("Calculation Exchange Rate must be greater than zero"))

    for target, source in CONVERTED_TOTALS.items():
        doc.set(target, flt(flt(doc.get(source)) * rate, doc.precision(target)))
