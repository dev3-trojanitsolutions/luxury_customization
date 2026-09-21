import frappe


@frappe.whitelist(allow_guest=True)
def get_employee_name(employee):
	return frappe.db.get_value("Employee", employee, "employee_name")
