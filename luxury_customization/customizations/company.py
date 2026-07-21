import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

def create_custom_fields():
    custom_fields = {
        "Company": [
            {
                "fieldname": "company_logos",
                "fieldtype": "Attach Image",
                "label": "Company Logo",
                "insert_after": "default_holiday_list",
                "reqd": 0
            },
            {
                "fieldname": "notify_days",
                "fieldtype": "Int",
                "label": "Notify Days",
                "insert_after": "company_logos",
                "reqd": 0
            },
            {
                "fieldname": "notify_userd",
                "fieldtype": "Table MultiSelect",
                "label": "Notify Users",
                "insert_after": "company_logos",
                "options": "Cheque Tracker Settings User",
                "reqd": 0
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
    custom_fields_to_delete = { "Company": ["company_logos", "notify_days", "notify_userd"] }  

    for doctype, fields in custom_fields_to_delete.items(): 
        for field_name in fields: 
            if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field_name}): 
                frappe.delete_doc("Custom Field", f"{doctype}-{field_name}", ignore_missing=True) 
                frappe.db.commit() 
                frappe.clear_cache(doctype=doctype)      