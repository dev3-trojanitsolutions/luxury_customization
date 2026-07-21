frappe.ui.form.on("Company", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Documents"), function () {
				frappe.set_route("List", "Company Documents", { company: frm.doc.name });
			});
		}
	},
});
