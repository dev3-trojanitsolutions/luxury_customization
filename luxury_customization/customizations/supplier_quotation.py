import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from erpnext.setup.utils import get_exchange_rate
from frappe.utils import flt

# Display-only: reads the standard base_* (company currency) totals and never writes to them.
CONVERTED_TOTALS = {
    "additional_net_total": "base_net_total",
    "additional_total": "base_total",
    "additional_grand_total": "base_grand_total",
}
INPUT_FIELDS = ["multi_currency_calculation", "calculation_currency", "calculation_exchange_rate", "calculation_to_document_rate"]
ITEM_SOURCES = []  # (item link field, source item doctype)

def create_custom_fields():
    custom_fields = {
        "Supplier Quotation": [
            {
                "fieldname": "calculation_to_document_rate",
                "fieldtype": "Float",
                "label": "Calculation → Document Currency Rate",
                "allow_on_submit": 1,
                "precision": "9",
                "insert_after": "buying_price_list",
                "depends_on": "eval:doc.multi_currency_calculation && doc.calculation_currency",
                "description": "Document currency per 1 unit of Calculation Currency",
            },
            {
                "fieldname": "additional_currency_section",
                "fieldtype": "Section Break",
                "label": "Additional Currency Calculation",
                "insert_after": "disable_rounded_total",
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
                "description": "Company currency per 1 unit of Calculation Currency",
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
        ],
        "Supplier Quotation Item": [
            {
                "fieldname": "other_currency_rate",
                "fieldtype": "Currency",
                "label": "Other Currency Rate",
                "options": "calculation_currency",
                "insert_after": "rate",
                "in_list_view": 1,
                "depends_on": "eval:parent.multi_currency_calculation",
                "description": "Item price in Calculation Currency",
            },
        ],
    }

    for doctype, fields in custom_fields.items():
        for field in fields:
            if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field["fieldname"]}):
                create_custom_field(doctype, field)
                frappe.db.commit()
                frappe.clear_cache(doctype=doctype)

def delete_custom_fields():
    custom_fields_to_delete = {
        "Supplier Quotation": [
            "additional_currency_section", "multi_currency_calculation", "calculation_currency",
            "calculation_exchange_rate", "calculation_to_document_rate", "additional_currency_column", "additional_net_total",
            "additional_total", "additional_grand_total",
        ],
        "Supplier Quotation Item": ["other_currency_rate"],
    }

    for doctype, fields in custom_fields_to_delete.items():
        for field_name in fields:
            if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field_name}):
                frappe.delete_doc("Custom Field", f"{doctype}-{field_name}", ignore_missing=True)
                frappe.db.commit()
                frappe.clear_cache(doctype=doctype)

def additional_totals(doc, rate):
    # (net total, total, grand total) in calculation currency. Rows priced in that currency use the
    # entered price exactly; other rows, taxes and rounding convert from the base_* amounts.
    total = net = 0
    for row in doc.items:
        entered = flt(row.get("other_currency_rate")) * flt(row.qty)
        if entered > 0:
            total += entered
            net += entered * (flt(row.base_net_amount) / flt(row.base_amount) if flt(row.base_amount) else 1)
        else:
            total += flt(row.base_amount) / rate
            net += flt(row.base_net_amount) / rate
    return net, total, net + (flt(doc.base_grand_total) - flt(doc.base_net_total)) / rate

def validate(doc, method=None):
    if not doc.multi_currency_calculation:
        for target in CONVERTED_TOTALS:
            doc.set(target, 0)
        return

    if not doc.calculation_currency:
        frappe.throw(_("Please select a Calculation Currency"))

    rate = flt(doc.calculation_exchange_rate)
    if rate <= 0:
        frappe.throw(_("Calculation Exchange Rate must be greater than zero"))

    for target, value in zip(CONVERTED_TOTALS, additional_totals(doc, rate)):
        doc.set(target, flt(value, doc.precision(target)))

def copy_item_rates(doc):
    # Mapped item rows only carry mapped fields, so pick other_currency_rate up from the source row.
    if not doc.is_new():
        return
    for row in doc.items:
        if flt(row.get("other_currency_rate")):
            continue
        for field, source_doctype in ITEM_SOURCES:
            if row.get(field):
                row.other_currency_rate = frappe.db.get_value(source_doctype, row.get(field), "other_currency_rate") or 0
                break

def fetch_document_rate(doc):
    # Live Calculation Currency -> document currency rate, stored so the user can still override it.
    if not (doc.calculation_currency and doc.currency):
        return 0
    doc.calculation_to_document_rate = flt(get_exchange_rate(doc.calculation_currency, doc.currency, doc.get("transaction_date")))
    return doc.calculation_to_document_rate

def before_validate(doc, method=None):
    # Runs before ERPNext's own validate, so its normal Rate x Qty, tax and base_* logic takes over.
    copy_item_rates(doc)
    if not doc.multi_currency_calculation:
        return

    rate = flt(doc.calculation_exchange_rate)
    conversion_rate = flt(doc.conversion_rate) or 1
    to_document_rate = flt(doc.get("calculation_to_document_rate")) or fetch_document_rate(doc)
    for row in doc.items:
        if flt(row.get("other_currency_rate")) <= 0:
            continue
        if to_document_rate:
            price = flt(row.other_currency_rate) * to_document_rate
        else:
            if rate <= 0:
                frappe.throw(_("Calculation Exchange Rate must be greater than zero"))
            # Fallback: other rate x (company currency per 1 calc currency) / conversion rate
            price = flt(row.other_currency_rate) * rate / conversion_rate
        row.price_list_rate = flt(price, row.precision("rate"))
        row.rate = row.price_list_rate
