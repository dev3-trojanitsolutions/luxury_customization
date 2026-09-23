import frappe


@frappe.whitelist(allow_guest=True)
def get_employee_details(employee):
	return frappe.db.get_value(
		"Employee", employee, ["employee_name", "employee_number", "name"], as_dict=True
	)


@frappe.whitelist(allow_guest=True)
def get_employee_info(employee):
	emp = frappe.db.get_value(
		"Employee", employee, ["name", "employee_name", "employee_number"], as_dict=True
	)
	if emp:
		return {
			"name": emp["name"],
			"employee_name": emp["employee_name"],
			"employee_code": emp["employee_number"]
		}
	return {}


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


@frappe.whitelist(allow_guest=True)
def get_employees_bulk(employee_codes):
	if not employee_codes:
		return []
	employees = frappe.db.get_all(
		"Employee",
		filters={"name": ["in", employee_codes]},
		fields=["name", "employee_name"]
	)
	return {emp["name"]: emp["employee_name"] for emp in employees}
