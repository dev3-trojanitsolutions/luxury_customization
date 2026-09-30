import json

import frappe


def get_context(context):
	employee_field = next(
		(f for f in context.web_form_doc.web_form_fields if f.fieldname == "employee"), None
	)
	if not employee_field:
		return

	filters = {}
	if frappe.session.user != "Guest":
		# Logged-in users only ever see their own Employee record.
		filters["user_id"] = frappe.session.user
	employees = frappe.get_all("Employee", filters=filters, fields=["name", "employee_name"])
	employee_field.options = json.dumps(
		[{"value": e.name, "label": e.name, "description": e.employee_name} for e in employees]
	)
