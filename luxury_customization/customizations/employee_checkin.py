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

def link_employee_checkin_image_field(doc, method):
	# web_form.accept() (frappe core) creates the employee_image File with
	# attached_to_doctype/attached_to_name set but leaves attached_to_field
	# blank. Core's own on_update hook (attach_files_to_document) then can't
	# recognize this File as "already attached" (it only reuses a File whose
	# attached_to_* are ALL blank) and creates a second, fully-linked File for
	# the same upload. Filling attached_to_field here, before that check runs,
	# makes the first File already match so no duplicate gets created.
	if doc.attached_to_doctype == "Employee Checkin" and doc.attached_to_name and not doc.attached_to_field:
		doc.attached_to_field = "employee_image"

def make_employee_image_public(doc, method):
	# Single choke point: catches private employee_image files regardless of
	# how they were uploaded (web form camera capture, Desk attach dialog, API).
	if not doc.employee_image:
		return

	private_files = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name,
			"attached_to_field": "employee_image",
			"is_private": 1,
		},
		pluck="name",
	)
	for file_name in private_files:
		file_doc = frappe.get_doc("File", file_name)
		file_doc.is_private = 0
		file_doc.save(ignore_permissions=True)

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