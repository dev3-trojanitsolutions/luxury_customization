import json

import frappe


def get_context(context):
	employee_field = next(
		(f for f in context.web_form_doc.web_form_fields if f.fieldname == "employee"), None
	)
	if not employee_field:
		return

	employees = frappe.get_all("Employee", fields=["name", "employee_name"])
	employee_field.options = json.dumps(
		[{"value": e.name, "label": e.name, "description": e.employee_name} for e in employees]
	)
