// Create > Purchase Invoice, same flow as ERPNext's Create > Purchase Order.
(function () {
	const MAKE_PI = "luxury_customization.api.material_request.make_purchase_invoice";

	function open_invoice(frm, supplier) {
		frappe.model.open_mapped_doc({ method: MAKE_PI, frm: frm, args: { supplier: supplier || null }, run_link_triggers: true });
	}

	// One invoice has one supplier, so ask for it when the items have different default suppliers.
	function select_supplier(frm, suppliers) {
		const d = new frappe.ui.Dialog({
			title: __("Select Supplier"),
			fields: [{ fieldname: "supplier", fieldtype: "Link", options: "Supplier", label: __("Supplier"), reqd: 1, default: suppliers[0] }],
			primary_action_label: __("Create"),
			primary_action: (values) => {
				d.hide();
				open_invoice(frm, values.supplier);
			},
		});
		d.show();
	}

	function make_purchase_invoice(frm) {
		frappe.call({
			method: "erpnext.stock.doctype.material_request.material_request.get_item_default_suppliers",
			args: { source_name: frm.doc.name, filtered_children: (frm.get_selected() || {}).items || [] },
			freeze: true,
			callback: (r) => {
				const suppliers = [...new Set((r.message || []).map((item) => item.supplier).filter(Boolean))];
				if (suppliers.length > 1) select_supplier(frm, suppliers);
				else open_invoice(frm, suppliers[0]);
			},
		});
	}

	frappe.ui.form.on("Material Request", {
		refresh(frm) {
			const d = frm.doc;
			const precision = frappe.defaults.get_default("float_precision");
			if (d.docstatus !== 1 || d.status === "Stopped" || d.material_request_type !== "Purchase") return;
			if (flt(d.per_ordered, precision) >= 100) return;
			frm.add_custom_button(__("Purchase Invoice"), () => make_purchase_invoice(frm), __("Create"));
		},
	});
})();
