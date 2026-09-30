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



@frappe.whitelist()
def get_my_employee():
	# Standard link: Employee.user_id -> User. Active record preferred.
	return frappe.db.get_value(
		"Employee", {"user_id": frappe.session.user}, "name", order_by="status asc, creation asc"
	)
