frappe.ready(function () {
	frappe.web_form.set_value("time", frappe.datetime.now_datetime());

	frappe.web_form.on("employee", (field, value) => {
		if (!value) {
			frappe.web_form.set_value("employee_name", "");
			return;
		}
		frappe.call({
			method: "luxury_customization.api.employee_checkin.get_employee_name",
			args: { employee: value },
			callback: (r) => {
				frappe.web_form.set_value("employee_name", r.message || "");
			},
		});
	});


	frappe.web_form.validate = () => {
		frappe.web_form.set_value("time", frappe.datetime.now_datetime());

		if (frappe.web_form.get_value("employee") && !frappe.web_form.get_value("employee_image")) {
			frappe.msgprint(__("Please upload your image before submitting Employee Checkin."));
			return false;
		}
		return true;
	};
});