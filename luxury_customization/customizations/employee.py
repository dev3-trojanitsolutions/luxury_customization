import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

def create_custom_fields():
    custom_fields = {
        "Employee": [
            {
                "fieldname": "wps_required",
                "fieldtype": "Select",
                "label": "WPS Required",
                "insert_after": "payroll_cost_center",
                "reqd": 1,
                "options": "\nYes\nNo"
            },
                {
                "fieldname": "wps_id",
                "fieldtype": "Data",
                "label": "WPS ID",
                "insert_after": "wps_required",
                "depends_on": "eval:doc.wps_required == 'Yes'",
                "mandatory_depends_on": "eval:doc.wps_required == 'Yes'"
                
            }
        ]
    }

    for doctype, fields in custom_fields.items(): 
        for field in fields: 
            if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field["fieldname"]}):
                create_custom_field(doctype, field) 
                frappe.db.commit() 
                frappe.clear_cache(doctype=doctype)

def delete_custom_fields(): 
    custom_fields_to_delete = { "Employee": ["wps_required","wps_id"] }  

    for doctype, fields in custom_fields_to_delete.items(): 
        for field_name in fields: 
            if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field_name}): 
                frappe.delete_doc("Custom Field", f"{doctype}-{field_name}", ignore_missing=True) 
                frappe.db.commit() 
                frappe.clear_cache(doctype=doctype)      