import frappe


@frappe.whitelist(allow_guest=True)
def get_employee_details(employee):
	return frappe.db.get_value(
		"Employee", employee, ["employee_name", "employee_number"], as_dict=True
	)


@frappe.whitelist(allow_guest=True)
def get_employees_with_name(doctype, txt, searchfield, start, page_length, filters=None):
	conditions = []
	if txt:
		conditions.append(f"({searchfield} like {frappe.db.escape(f'%{txt}%')} OR employee_name like {frappe.db.escape(f'%{txt}%')})")

	condition_str = " and ".join(conditions) if conditions else "1=1"

	employees = frappe.db.sql(
		f"""
		SELECT name, employee_name
		FROM `tabEmployee`
		WHERE {condition_str}
		LIMIT {page_length} OFFSET {start}
		""",
		as_dict=True
	)

	return [[emp['name'], f"<div style='line-height: 1.5;'><strong>{emp['name']}</strong><br/>{emp['employee_name']}</div>"] for emp in employees]
