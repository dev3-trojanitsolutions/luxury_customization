from frappe.custom.doctype.property_setter.property_setter import make_property_setter

ITEM_DOCTYPES = ["Purchase Order Item", "Purchase Receipt Item", "Purchase Invoice Item", "Supplier Quotation Item"]
RATE_FIELDS = ["rate", "price_list_rate", "net_rate", "base_rate", "base_price_list_rate", "base_net_rate"]
PRECISION = "6"  # ponytail: fixed 6; enough for sub-cent RMB->USD prices

def set_rate_precision():
    # Keeps converted unit prices (e.g. 0.0645) from being rounded to 2 decimals.
    for doctype in ITEM_DOCTYPES:
        for field in RATE_FIELDS:
            make_property_setter(doctype, field, "precision", PRECISION, "Select", validate_fields_for_doctype=False)
