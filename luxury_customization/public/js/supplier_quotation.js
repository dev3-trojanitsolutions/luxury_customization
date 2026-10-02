// Display-only: reads the standard base_* totals and writes only the additional_* fields.
(function () {
	const CONVERTED_TOTALS = {
		additional_net_total: "base_net_total",
		additional_total: "base_total",
		additional_grand_total: "base_grand_total",
	};

	function set_rate_label(frm) {
		const company_currency = frm.doc.company ? erpnext.get_currency(frm.doc.company) : "";
		const label = frm.doc.calculation_currency && company_currency
			? __("Calculation Exchange Rate (1 {0} = ? {1})", [company_currency, frm.doc.calculation_currency])
			: __("Calculation Exchange Rate");
		frm.set_df_property("calculation_exchange_rate", "label", label);
	}

	function calculate_additional_currency(frm) {
		if (frm.doc.docstatus > 1) return;

		const rate = flt(frm.doc.calculation_exchange_rate);
		const enabled = frm.doc.multi_currency_calculation && frm.doc.calculation_currency && rate > 0;

		Object.entries(CONVERTED_TOTALS).forEach(([target, source]) => {
			const value = enabled ? flt(flt(frm.doc[source]) * rate, precision(target, frm.doc)) : 0;
			if (flt(frm.doc[target]) !== value) frm.set_value(target, value);
		});
	}

	frappe.ui.form.on("Supplier Quotation", {
		refresh(frm) {
			set_rate_label(frm);
			calculate_additional_currency(frm);
		},
		multi_currency_calculation: calculate_additional_currency,
		calculation_currency(frm) {
			set_rate_label(frm);
			calculate_additional_currency(frm);
		},
		calculation_exchange_rate: calculate_additional_currency,
		// ERPNext sets these whenever items, qty, rate, discount or taxes change
		base_net_total: calculate_additional_currency,
		base_total: calculate_additional_currency,
		base_grand_total: calculate_additional_currency,
	});
})();
