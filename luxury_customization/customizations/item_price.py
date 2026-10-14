import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

def create_custom_fields():
    custom_fields = {
        "Price List": [
            {
                "fieldname": "branch",
                "fieldtype": "Link",
                "label": "Branch",
                "insert_after": "price_not_uom_dependent",
                "options": "Branch",
            }
        ]
    }

    for doctype, fields in custom_fields.items():
        for field in fields:
            cf_name = f"{doctype}-{field['fieldname']}"
            if frappe.db.exists("Custom Field", cf_name):
                frappe.db.set_value("Custom Field", cf_name, {"fieldtype": field["fieldtype"]})
            else:
                create_custom_field(doctype, field)
            frappe.db.commit()
            frappe.clear_cache(doctype=doctype)

def delete_custom_fields(): 
    custom_fields_to_delete = { "Price List": ["branch"] }  

    for doctype, fields in custom_fields_to_delete.items(): 
        for field_name in fields: 
            if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field_name}): 
                frappe.delete_doc("Custom Field", f"{doctype}-{field_name}", ignore_missing=True) 
                frappe.db.commit() 
                frappe.clear_cache(doctype=doctype)      