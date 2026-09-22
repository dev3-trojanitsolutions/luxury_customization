import frappe


@frappe.whitelist(allow_guest=True)
def get_employee_details(employee):
	return frappe.db.get_value(
		"Employee", employee, ["employee_name", "employee_number"], as_dict=True
	)
