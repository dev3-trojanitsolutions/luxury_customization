import frappe
from frappe.desk.reportview import get_filters_cond, get_match_cond


@frappe.whitelist(allow_guest=True)
def get_employee_details(employee):
	return frappe.db.get_value(
		"Employee", employee, ["employee_name", "employee_number"], as_dict=True
	)


@frappe.whitelist(allow_guest=True)
@frappe.validate_and_sanitize_search_inputs
def employee_query(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	doctype = "Employee"
	conditions = []
	return frappe.db.sql(
		"""select name, employee_name
		from `tabEmployee`
		where (name like %(txt)s or employee_name like %(txt)s)
			{fcond} {mcond}
		order by idx desc, name
		limit %(page_len)s offset %(start)s""".format(
			fcond=get_filters_cond(doctype, filters, conditions),
			mcond=get_match_cond(doctype),
		),
		{"txt": f"%{txt}%", "start": start, "page_len": page_len},
	)
