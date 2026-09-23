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

@frappe.whitelist(methods=["POST", "PUT"], allow_guest=True)
def accept(web_form: str, data, web_form_request_key: str | None = None):
    # Guest submissions to employee-checkin fail to save the Attach Image
    # field: web_form.accept() saves the File without ignore_permissions,
    # and File.has_permission (frappe core) then requires *write* on the
    # just-inserted Employee Checkin, which Guest never has. Elevating only
    # for this one form, only for Guest, for the duration of the original
    # handler mirrors dms.api.sales._submit_as_admin.
    from frappe.website.doctype.web_form.web_form import accept as _accept

    if web_form != "employee-checkin" or frappe.session.user != "Guest":
        return _accept(web_form=web_form, data=data, web_form_request_key=web_form_request_key)

    _user = frappe.session.user
    frappe.session.user = "Administrator"
    frappe.local.role_permissions = {}
    frappe.local.user_perms = None
    try:
        return _accept(web_form=web_form, data=data, web_form_request_key=web_form_request_key)
    finally:
        frappe.session.user = _user
        frappe.local.role_permissions = {}
        frappe.local.user_perms = None

def delete_custom_fields():
    custom_fields_to_delete = { "Employee Checkin": ["employee_code", "employee_image"] }

    for doctype, fields in custom_fields_to_delete.items():
        for field_name in fields:
            if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field_name}):
                frappe.delete_doc("Custom Field", f"{doctype}-{field_name}", ignore_missing=True)
                frappe.db.commit()
                frappe.clear_cache(doctype=doctype)      