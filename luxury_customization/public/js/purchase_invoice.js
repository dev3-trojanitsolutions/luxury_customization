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
			? __("Calculation Exchange Rate (1 {0} = ? {1})", [frm.doc.calculation_currency, company_currency])
			: __("Calculation Exchange Rate");
		frm.set_df_property("calculation_exchange_rate", "label", label);
	}

	// (net total, total, grand total): rows priced in the calculation currency use the entered price exactly,
	// other rows, taxes and rounding convert from the base_* amounts.
	function additional_totals(frm, rate) {
		let total = 0, net = 0;
		(frm.doc.items || []).forEach((row) => {
			const entered = flt(row.other_currency_rate) * flt(row.qty);
			if (entered > 0) {
				total += entered;
				net += entered * (flt(row.base_amount) ? flt(row.base_net_amount) / flt(row.base_amount) : 1);
			} else {
				total += flt(row.base_amount) / rate;
				net += flt(row.base_net_amount) / rate;
			}
		});
		return [net, total, net + (flt(frm.doc.base_grand_total) - flt(frm.doc.base_net_total)) / rate];
	}

	function calculate_additional_currency(frm) {
		if (frm.doc.docstatus > 1) return;

		const rate = flt(frm.doc.calculation_exchange_rate);
		const enabled = frm.doc.multi_currency_calculation && frm.doc.calculation_currency && rate > 0;

		const totals = enabled ? additional_totals(frm, rate) : [0, 0, 0];
		Object.keys(CONVERTED_TOTALS).forEach((target, i) => {
			const value = flt(totals[i], precision(target, frm.doc));
			if (flt(frm.doc[target]) !== value) frm.set_value(target, value);
		});
	}

	frappe.ui.form.on("Purchase Invoice", {
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

(function () {
	// Items table: Other Currency Rate x Calculation Exchange Rate / conversion rate -> standard Price List Rate.
	// ERPNext's own handlers then work out Rate, Amount, taxes and totals.
	function convert_row(frm, row) {
		const rate = flt(frm.doc.calculation_exchange_rate);
		if (!frm.doc.multi_currency_calculation || frm.doc.docstatus !== 0) return;
		if (flt(row.other_currency_rate) <= 0 || rate <= 0) return;

		const value = flt(flt(row.other_currency_rate) * rate / (flt(frm.doc.conversion_rate) || 1), precision("price_list_rate", row));
		if (flt(row.price_list_rate) !== value) frappe.model.set_value(row.doctype, row.name, "price_list_rate", value);
	}

	function convert_all_rows(frm) {
		(frm.doc.items || []).forEach((row) => convert_row(frm, row));
	}

	frappe.ui.form.on("Purchase Invoice", {
		multi_currency_calculation: convert_all_rows,
		calculation_exchange_rate: convert_all_rows,
		conversion_rate: convert_all_rows,
	});

	frappe.ui.form.on("Purchase Invoice Item", {
		other_currency_rate(frm, cdt, cdn) {
			convert_row(frm, locals[cdt][cdn]);
		},
	});
})();

(function () {
	// Ask once per opened draft whether to use multi currency calculation.
	frappe.ui.form.on("Purchase Invoice", {
		refresh(frm) {
			if (frm.doc.docstatus !== 0 || frm.doc.multi_currency_calculation || frm._mc_prompted === frm.doc.name) return;
			frm._mc_prompted = frm.doc.name;
			frappe.confirm(__("Do you want to use Multi Currency Calculation for this document?"), () =>
				frm.set_value("multi_currency_calculation", 1)
			);
		},
	});
})();
