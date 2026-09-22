import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

def create_custom_fields():
    custom_fields = {
        "Employee Checkin": [
            {
                "fieldname": "employee_code",
                "fieldtype": "Data",
                "label": "Employee Code",
                "insert_after": "employee",
                "read_only": 1,
                "reqd": 0
            },
            {
                "fieldname": "employee_image",
                "fieldtype": "Attach Image",
                "label": "Employee Image",
                "insert_after": "attendance",
                "reqd": 0,
                "mandatory_depends_on": "eval:doc.employee"
            }
        ]
    }

    for doctype, fields in custom_fields.items(): 
        for field in fields: 
            if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field["fieldname"]}):
                create_custom_field(doctype, field) 
                frappe.db.commit() 
                frappe.clear_cache(doctype=doctype)

def set_check_in_time(doc, method):
	doc.time = frappe.utils.now_datetime()

def delete_custom_fields():
    custom_fields_to_delete = { "Employee Checkin": ["employee_code", "employee_image"] }

    for doctype, fields in custom_fields_to_delete.items():
        for field_name in fields:
            if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field_name}):
                frappe.delete_doc("Custom Field", f"{doctype}-{field_name}", ignore_missing=True)
                frappe.db.commit()
                frappe.clear_cache(doctype=doctype)      