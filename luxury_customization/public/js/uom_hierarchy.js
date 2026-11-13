// "+ UOM" on purchase item rows. The user keeps a free list of UOMs; each line says what one unit
// contains, in any other UOM or the stock UOM ("1 Carton = 10 Box", "1 Box = 24 Nos", "1 Bag = 50 Nos").
// Then a quantity and a buying / selling price per UOM. The row is posted as uom / conversion_factor /
// qty with the blended rate, and ERPNext computes stock_qty, valuation and accounting as usual.
// Server side: customizations/uom_hierarchy.py (same JSON format and the same calculation).
frappe.provide("luxury.uom_hierarchy");

(function () {
	const ns = luxury.uom_hierarchy;
	const CHILD_DOCTYPES = [
		"Purchase Order Item",
		"Purchase Receipt Item",
		"Purchase Invoice Item",
		"Supplier Quotation Item",
	];
	const METHOD = "luxury_customization.customizations.uom_hierarchy.";
	const CF_PRECISION = 9;
	const esc = (s) => frappe.utils.escape_html(s || "");
	const fmt = (n) => format_number(n, null, flt(n) % 1 ? 3 : 0);
	const money = (n) => format_number(n, null, 2);

	// --- Calculation (same rules as conversion_factors()/compute() in uom_hierarchy.py) ---------------

	// Earlier rows were a chain (top first, per_parent = how many in one of the level above).
	function normalize(levels) {
		if (levels.some((l) => "inner" in l) || !levels.some((l) => "per_parent" in l)) return levels;
		return levels.map((l, i) => {
			const below = levels[i + 1];
			const { per_parent, ...rest } = l;
			return below ? { ...rest, inner: below.uom, contains: flt(below.per_parent) } : rest;
		});
	}

	// levels: [{uom, inner, contains, qty, rate, selling_price}], the stock UOM among them.
	function calculate(levels, stock_uom) {
		const result = { levels, stock_uom, factors: [], total: 0, posting: null, error: null };
		const by_uom = {};
		for (const l of levels) {
			if (!l.uom) return { ...result, error: __("Pick a UOM on every line") };
			if (by_uom[l.uom]) return { ...result, error: __("UOM {0} is used twice", [l.uom]) };
			by_uom[l.uom] = l;
		}
		const factor = (uom, path) => {
			if (uom === stock_uom) return 1;
			const l = by_uom[uom];
			if (!l) throw __("{0} is not in the list", [uom]);
			if (path.includes(uom)) throw __("{0} contains itself", [[...path, uom].join(" > ")]);
			if (!l.inner) throw __("Say what 1 {0} contains", [uom]);
			if (flt(l.contains) <= 0) throw __("Enter how many {0} are in 1 {1}", [l.inner, uom]);
			return flt(l.contains) * factor(l.inner, [...path, uom]);
		};
		let factors;
		try {
			factors = levels.map((l) => flt(factor(l.uom, []), CF_PRECISION));
		} catch (error) {
			return { ...result, error };
		}
		const small = levels.find((l, i) => factors[i] < 1);
		if (small) return { ...result, error: __("{0} is smaller than the stock UOM {1}", [small.uom, stock_uom]) };

		levels.forEach((l, i) => (result.total += flt(l.qty) * factors[i]));
		const used = levels.map((l, i) => i).filter((i) => flt(levels[i].qty) > 0);
		if (used.length) {
			let posting = used.reduce((a, b) => (factors[b] < factors[a] ? b : a));
			const qty = result.total / factors[posting];
			// e.g. 1 Bag (50) + 1 Box (24) = 74 Nos is no whole number of Boxes: post in the stock UOM
			if (Math.abs(qty - Math.round(qty)) > 1e-9) posting = levels.findIndex((l) => l.uom === stock_uom);
			result.posting = posting;
		}
		return { ...result, factors };
	}

	// Always one line for the stock UOM, last.
	function with_stock(levels, stock_uom) {
		const stock = levels.find((l) => l.uom === stock_uom) || { uom: stock_uom, qty: 0 };
		return [...levels.filter((l) => l.uom !== stock_uom), { ...stock, inner: undefined, contains: undefined }];
	}

	// Item UOMs, largest first. Each one contains the largest smaller UOM that fits it a whole number
	// of times (Carton 240 = 10 Box of 24), else the stock UOM (Bag 50 = 50 Nos).
	function levels_from_item(info) {
		const uoms = (info.uoms || [])
			.filter((d) => d.uom !== info.stock_uom && flt(d.conversion_factor) >= 1)
			.sort((a, b) => flt(b.conversion_factor) - flt(a.conversion_factor));
		const levels = uoms.map((d, i) => {
			const cf = flt(d.conversion_factor);
			const inner = uoms.slice(i + 1).find((s) => {
				const n = cf / flt(s.conversion_factor);
				return flt(s.conversion_factor) < cf && Math.abs(n - Math.round(n)) < 1e-9;
			});
			return inner
				? { uom: d.uom, inner: inner.uom, contains: Math.round(cf / flt(inner.conversion_factor)), qty: 0 }
				: { uom: d.uom, inner: info.stock_uom, contains: cf, qty: 0 };
		});
		return with_stock(levels, info.stock_uom);
	}

	function saved_levels(row, info) {
		try {
			const saved = row.uom_hierarchy ? JSON.parse(row.uom_hierarchy) : null;
			if (saved && saved.stock_uom === info.stock_uom && (saved.levels || []).length) {
				return with_stock(normalize(saved.levels), info.stock_uom);
			}
		} catch (e) {
			// fall through to the Item's UOMs
		}
		return null;
	}

	function initial_levels(row, info) {
		let levels = saved_levels(row, info);
		if (levels) {
			levels = levels.map((l) => ({ ...l }));
			// Row edited outside the dialog (e.g. partial receipt): show the row's own qty on its UOM.
			const calc = calculate(levels, info.stock_uom);
			const posted = !calc.error && calc.posting !== null
				&& levels[calc.posting].uom === row.uom
				&& Math.abs(calc.total / calc.factors[calc.posting] - flt(row.qty)) < 1e-6;
			if (!posted && levels.some((l) => l.uom === row.uom)) {
				levels.forEach((l) => (l.qty = l.uom === row.uom ? flt(row.qty) : 0));
			} else if (!posted) {
				levels = null;
			}
		}
		if (!levels) {
			const known = (info.uoms || []).some((d) => d.uom === row.uom);
			if (row.uom && row.uom !== info.stock_uom && !known && flt(row.conversion_factor) > 1) {
				info.uoms = [...(info.uoms || []), { uom: row.uom, conversion_factor: flt(row.conversion_factor) }];
			}
			levels = levels_from_item(info);
			// The row's current UOM (the Item's Purchase UOM on a new row) gets the row qty.
			const current = levels.find((l) => l.uom === (row.uom || info.purchase_uom));
			if (current) current.qty = flt(row.qty);
		}
		// Item Prices for UOMs without a price of their own on this row
		levels.forEach((l) => {
			if (!flt(l.rate) && info.buying_prices[l.uom]) l.rate = info.buying_prices[l.uom];
			if (!flt(l.selling_price) && info.selling_prices[l.uom]) l.selling_price = info.selling_prices[l.uom];
		});
		return levels;
	}

	// --- Prices ---------------------------------------------------------------------------------------

	const rate_field = (frm) => (frm.doc.multi_currency_calculation ? "other_currency_rate" : "rate");
	const entry_currency = (frm) =>
		frm.doc.multi_currency_calculation ? frm.doc.calculation_currency : frm.doc.currency;

	// Price per stock unit, used to suggest a price (placeholder) for levels without one.
	function per_stock_prices(frm, row, info) {
		const cf = flt(row.conversion_factor) || 1;
		return {
			rate: flt(row[rate_field(frm)]) / cf || flt(info.buying_prices[info.stock_uom]),
			selling_price: flt(row.selling_price) / cf || flt(info.selling_prices[info.stock_uom]),
		};
	}

	// Typed price, else the suggested one (per stock unit x CF).
	const price_of = (level, field, cf, per_stock) => flt(level[field]) || flt(per_stock[field] * cf);

	function amount_of(calc, per_stock) {
		return calc.levels.reduce((sum, l, i) => sum + flt(l.qty) * price_of(l, "rate", calc.factors[i], per_stock), 0);
	}

	// --- Dialog ---------------------------------------------------------------------------------------

	function open_dialog(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code) {
			frappe.show_alert({ message: __("Select an item first"), indicator: "orange" });
			return;
		}
		frappe.call({
			method: METHOD + "get_item_uom_info",
			args: {
				item_code: row.item_code,
				buying_price_list: frm.doc.buying_price_list,
				buying_currency: entry_currency(frm),
				sell_price_list: row.sell_price_list,
				company: frm.doc.company,
			},
		}).then((r) => {
			const info = r.message || {};
			if (!info.stock_uom) return;
			info.buying_prices = info.buying_prices || {};
			info.selling_prices = info.selling_prices || {};
			if (frm.doc.docstatus !== 0) {
				const levels = initial_levels(row, info);
				const calc = calculate(levels, info.stock_uom);
				frappe.msgprint({
					title: __("UOM Levels: {0}", [row.item_code]),
					message: packing_html(calc, info.stock_uom) + summary_html(frm, row, calc, info, per_stock_prices(frm, row, info)),
				});
				return;
			}
			new UOMDialog(frm, cdt, cdn, info).show();
		});
	}

	// Level indexes, largest UOM first.
	const by_size = (calc) => calc.levels.map((l, i) => i).sort((a, b) => calc.factors[b] - calc.factors[a]);

	// Read-only packing for submitted documents.
	function packing_html(calc, stock_uom) {
		if (calc.error) return "";
		const lines = calc.levels
			.filter((l) => l.uom !== stock_uom)
			.map((l) => `1 ${esc(l.uom)} = ${fmt(l.contains)} ${esc(l.inner)}`
				+ (l.inner === stock_uom ? "" : ` = ${fmt(calc.factors[calc.levels.indexOf(l)])} ${esc(stock_uom)}`));
		return `<div class="text-muted small">${lines.join("<br>")}</div>`;
	}

	function summary_html(frm, row, calc, info, per_stock) {
		if (calc.error) return `<div class="text-danger small mt-2">${esc(calc.error)}</div>`;
		const { levels, factors, total, posting } = calc;
		if (posting === null) return `<div class="small mt-2">${__("Enter what you are buying")}</div>`;
		const bought = levels
			.filter((l) => flt(l.qty) > 0)
			.map((l) => `${fmt(l.qty)} ${esc(l.uom)}`)
			.join(" + ");
		const qty = total / factors[posting];
		const amount = amount_of(calc, per_stock);
		const rate = qty ? flt(amount / qty, precision(rate_field(frm), row)) : 0;
		const lines = [`<div class="mt-2"><b>${__("Buying {0} = {1} {2}", [bought, fmt(total), esc(info.stock_uom)])}</b></div>`];
		lines.push(`<div class="text-muted small">${__(
			"Posted as {0} {1}, Conversion Factor {2}, Stock Qty {3} {4}",
			[fmt(qty), esc(levels[posting].uom), fmt(factors[posting]), fmt(total), esc(info.stock_uom)]
		)}</div>`);
		if (amount) {
			lines.push(`<div class="small">${__("Amount {0} {1} · Rate {2} per {3}", [
				esc(entry_currency(frm)), money(qty * rate), money(rate), esc(levels[posting].uom),
			])}</div>`);
		}
		return lines.join("");
	}

	class UOMDialog {
		constructor(frm, cdt, cdn, info) {
			this.frm = frm;
			this.cdt = cdt;
			this.cdn = cdn;
			this.row = locals[cdt][cdn];
			this.info = info;
			this.stock_uom = info.stock_uom;
			this.levels = initial_levels(this.row, info);
			this.per_stock = per_stock_prices(frm, this.row, info);
			this.has_selling = frappe.meta.has_field(cdt, "selling_price");
			// What is being bought: one UOM and a qty. The other UOMs show the same quantity converted.
			const calc = this.calc();
			// A saved / Item Price price that is not just "price per stock unit x size" is a special price: keep it fixed.
			if (!calc.error) {
				this.levels.forEach((l, i) => ["rate", "selling_price"].forEach((field) => {
					const linked = flt(this.per_stock[field] * calc.factors[i]);
					if (linked && flt(l[field]) && Math.abs(flt(l[field]) - linked) > 0.01) (l.typed = l.typed || {})[field] = true;
				}));
			}
			if (!calc.error && calc.posting !== null) {
				const uom = this.levels[calc.posting].uom;
				this.buy = { uom, qty: calc.total / calc.factors[calc.posting] };
			} else {
				const has = (u) => u && this.levels.some((l) => l.uom === u);
				this.buy = { uom: [this.row.uom, info.purchase_uom].find(has) || this.levels[0].uom, qty: 0 };
			}
			this.make();
		}

		make() {
			this.dialog = new frappe.ui.Dialog({
				title: __("UOM Levels: {0}", [this.row.item_code]),
				size: "large",
				fields: [
					{ fieldtype: "HTML", fieldname: "packing" },
					{ fieldtype: "HTML", fieldname: "quantities" },
					{ fieldtype: "HTML", fieldname: "summary" },
				],
				primary_action_label: __("Apply"),
				primary_action: () => this.apply(),
			});
		}

		show() {
			this.dialog.show();
			this.render();
		}

		calc() {
			return calculate(this.levels, this.stock_uom);
		}

		render() {
			this.render_packing();
			this.render_quantities();
			this.render_summary();
		}

		// One line per UOM: "1 [Carton] = [10] [Box]  = 240 Nos  ✕". Any order, any inner UOM.
		render_packing() {
			const $w = this.dialog.fields_dict.packing.$wrapper.empty();
			$w.append(`<div class="d-flex justify-content-between mb-2">
				<b>${__("Packing")}</b>
				<span class="text-muted small">${__("Stock UOM")}: <b>${esc(this.stock_uom)}</b></span>
			</div>`);
			this.size_spans = [];
			this.levels.forEach((level) => {
				if (level.uom === this.stock_uom) return;
				const $line = $(`<div class="d-flex align-items-center mb-2" style="gap: 8px">
					<span>1</span><div class="outer" style="width: 160px"></div><span>=</span>
					<div class="count" style="width: 90px"></div><div class="inner" style="width: 160px"></div>
					<span class="size text-muted small" style="min-width: 90px"></span>
				</div>`).appendTo($w);
				this.uom_control($line.find(".outer"), level.uom, (uom) => this.rename(level, uom),
					() => this.levels.map((l) => l.uom).filter((u) => u !== level.uom));
				this.float_control($line.find(".count"), level.contains, (v) => {
					level.contains = flt(v);
					this.update_sizes();
					this.render_quantities();
					this.render_summary();
				});
				this.uom_control($line.find(".inner"), level.inner, (uom) => {
					level.inner = uom;
					this.update_sizes();
					this.render_quantities();
					this.render_summary();
				}, () => [level.uom].filter(Boolean));
				this.size_spans.push([level, $line.find(".size")]);
				$(`<button class="btn btn-xs btn-default" title="${__("Remove")}">✕</button>`)
					.appendTo($line)
					.on("click", () => this.remove(level));
			});
			$(`<button class="btn btn-xs btn-default">${__("+ Add UOM")}</button>`)
				.appendTo($w)
				.on("click", () => {
					this.levels.splice(this.levels.length - 1, 0, { uom: "", inner: this.stock_uom, contains: 0, qty: 0 });
					this.render();
					this.dialog.fields_dict.packing.$wrapper.find(".outer input").last().focus();
				});
			$w.append("<hr>");
			this.update_sizes();
		}

		// "= 240 Nos" after each line, and Apply only when every line works out.
		update_sizes() {
			const calc = this.calc();
			this.size_spans.forEach(([level, $span]) => {
				const i = this.levels.indexOf(level);
				$span.text(!calc.error && level.inner !== this.stock_uom ? `= ${fmt(calc.factors[i])} ${this.stock_uom}` : "");
			});
			this.dialog.get_primary_btn().prop("disabled", !!calc.error);
		}

		rename(level, uom) {
			if (!uom || uom === level.uom) return;
			if (this.levels.some((l) => l !== level && l.uom === uom)) {
				frappe.show_alert({ message: __("{0} is already in the list", [uom]), indicator: "orange" });
				this.render();
				return;
			}
			const old = level.uom;
			// Lines that contained the old UOM now contain the new one.
			this.levels.forEach((l) => old && l.inner === old && (l.inner = uom));
			if (old && this.buy.uom === old) this.buy.uom = uom;
			level.uom = uom;
			if (!flt(level.rate)) level.rate = this.info.buying_prices[uom];
			if (!flt(level.selling_price)) level.selling_price = this.info.selling_prices[uom];
			this.render();
		}

		remove(level) {
			const users = this.levels.filter((l) => level.uom && l.inner === level.uom).map((l) => l.uom);
			if (users.length) {
				frappe.msgprint(__("{0} is inside {1}. Change those lines first.", [level.uom, users.join(", ")]));
				return;
			}
			this.levels = this.levels.filter((l) => l !== level);
			if (this.buy.uom === level.uom) this.buy = { uom: this.stock_uom, qty: 0 };
			this.render();
		}

		// Only the UOM being bought carries the qty in the stored levels.
		sync_buy() {
			this.levels.forEach((l) => (l.qty = l.uom === this.buy.uom ? flt(this.buy.qty) : 0));
		}

		// One table, largest UOM first. Qty is linked: typing 1 on Carton shows 5 on Box and 120 on Nos.
		render_quantities() {
			const $w = this.dialog.fields_dict.quantities.$wrapper.empty();
			if (!this.levels.some((l) => l.uom === this.buy.uom)) this.buy = { uom: this.stock_uom, qty: 0 };
			this.sync_buy();
			const calc = this.calc();
			if (calc.error) {
				$w.append(`<div class="text-danger small mb-2">${esc(calc.error)}</div>`);
				return;
			}
			const currency = esc(entry_currency(this.frm));
			const $table = $(`<table class="table table-bordered table-sm mb-0">
				<thead><tr>
					<th>${__("UOM")}</th><th style="width: 16%">${__("Qty")}</th>
					<th class="text-right" style="width: 11%">${__("{0} each", [esc(this.stock_uom)])}</th>
					<th style="width: 24%">${__("Buying Price")} (${currency})</th>
					${this.has_selling ? `<th style="width: 24%">${__("Selling Price")}</th>` : ""}
				</tr></thead><tbody></tbody>
				<tfoot><tr class="font-weight-bold">
					<td class="total-qty" colspan="3"></td><td class="total-rate text-right"></td>
					${this.has_selling ? '<td class="total-selling text-right"></td>' : ""}
				</tr></tfoot></table>`);
			$w.append(`<b class="d-block mb-1">${__("Quantity & Price")}</b>
				<div class="text-muted small mb-2">${__("Type the qty on the UOM you are buying; the other UOMs show the same quantity.")}</div>`)
				.append($table);
			this.$totals = $table.find("tfoot");
			this.cells = [];
			by_size(calc).forEach((i) => {
				const level = this.levels[i];
				const cf = calc.factors[i];
				const $tr = $(`<tr><td class="align-middle">${esc(level.uom)}</td><td class="qty"></td>
					<td class="text-right align-middle">${fmt(cf)}</td><td class="rate"></td>
					${this.has_selling ? '<td class="selling"></td>' : ""}</tr>`).appendTo($table.find("tbody"));
				const qty = this.float_control($tr.find(".qty"), 0, (v) => this.set_buy(level.uom, v));
				// Live while typing, not only when the field is left
				qty.$input.on("input", () => this.set_buy(level.uom, qty.$input.val(), qty));
				const price_control = (field, $td) => {
					// Prices not typed here follow the price per stock unit (also after a packing change).
					if (!(level.typed || {})[field] && flt(this.per_stock[field])) {
						level[field] = flt(this.per_stock[field] * cf, precision("rate", this.row));
					}
					const control = this.float_control($td, level[field], (v) => this.set_price(level, field, v, cf));
					control.$input.on("input", () => this.set_price(level, field, control.$input.val(), cf, control));
					return control;
				};
				const rate = price_control("rate", $tr.find(".rate"));
				const selling = this.has_selling ? price_control("selling_price", $tr.find(".selling")) : null;
				const amount = () => $(`<div class="text-muted small text-right"></div>`);
				this.cells.push({
					level, cf, $tr, qty, controls: { rate, selling_price: selling },
					rate: amount().appendTo($tr.find(".rate")),
					selling_price: this.has_selling ? amount().appendTo($tr.find(".selling")) : null,
				});
			});
			this.update_totals(calc);
		}

		// A typed price fixes that UOM's price and sets the price per stock unit; UOMs whose price was
		// not typed in this dialog follow it (Carton 24,000 -> Box 4,800 -> Nos 200).
		set_price(level, field, value, cf, typing) {
			const price = flt(value);
			if (flt(level[field]) === price && !typing) return;
			level[field] = price;
			(level.typed = level.typed || {})[field] = price > 0;
			if (price > 0) this.per_stock[field] = price / cf;
			(this.cells || []).forEach((cell) => {
				if (cell.level === level || (cell.level.typed || {})[field] || !cell.controls[field]) return;
				cell.level[field] = flt(this.per_stock[field] * cell.cf, precision("rate", this.row));
				cell.controls[field].set_input(cell.level[field] || "");
			});
			this.render_summary();
		}

		set_buy(uom, value, typing) {
			const qty = flt(value); // flt strips the number-format group separators from typed text
			if (this.buy.uom === uom && Math.abs(flt(this.buy.qty) - qty) < 1e-9 && !typing) return;
			this.buy = { uom, qty };
			this.sync_buy();
			this.typing = typing || null;
			this.render_summary();
		}

		// Linked qtys, the highlighted row, its amounts and the Total row.
		update_totals(calc) {
			if (!this.$totals || calc.error || !this.cells) return;
			const stock_qty = calc.total;
			const sums = { rate: 0, selling_price: 0 };
			this.cells.forEach((cell) => {
				const buying = cell.level.uom === this.buy.uom && flt(this.buy.qty) > 0;
				cell.$tr.toggleClass("table-active font-weight-bold", buying);
				// Every other row shows the same quantity in its own UOM (leave the field being typed in alone)
				if (cell.qty !== this.typing && !(cell.qty.$input && cell.qty.$input.is(":focus"))) {
					const value = stock_qty ? flt(stock_qty / cell.cf, 3) : 0;
					cell.qty.set_input(value || "");
				}
				["rate", "selling_price"].forEach((field) => {
					if (!cell[field]) return;
					const price = price_of(cell.level, field, cell.cf, this.per_stock);
					const qty = flt(cell.level.qty);
					if (buying) sums[field] = qty * price;
					cell[field].text(buying && price ? `${fmt(qty)} × ${money(price)} = ${money(qty * price)}` : "");
				});
			});
			this.$totals.find(".total-qty").text(flt(this.buy.qty)
				? `${__("Buying")}: ${fmt(this.buy.qty)} ${this.buy.uom}${this.buy.uom !== this.stock_uom ? ` = ${fmt(stock_qty)} ${this.stock_uom}` : ""}`
				: __("Type a qty on the UOM you are buying"));
			this.$totals.find(".total-rate").text(`${entry_currency(this.frm)} ${money(sums.rate)}`);
			this.$totals.find(".total-selling").text(money(sums.selling_price));
		}

		set_level(level, field, value) {
			level[field] = flt(value);
			this.render_summary();
		}

		render_summary() {
			const calc = this.calc();
			this.update_totals(calc);
			this.dialog.fields_dict.summary.$wrapper.html(
				calc.error ? "" : summary_html(this.frm, this.row, calc, this.info, this.per_stock)
			);
		}

		// exclude: function returning UOMs to leave out of the search
		uom_control($parent, value, on_change, exclude) {
			const control = frappe.ui.form.make_control({
				parent: $parent,
				df: {
					fieldtype: "Link",
					options: "UOM",
					fieldname: "uom",
					placeholder: __("UOM"),
					get_query: () => ({
						query: METHOD + "uom_query",
						filters: { item_code: this.row.item_code, exclude: exclude() },
					}),
					onchange: () => on_change(control.get_value()),
				},
				only_input: true,
				render_input: true,
			});
			control.set_input(value || "");
			return control;
		}

		float_control($parent, value, on_change, placeholder) {
			const control = frappe.ui.form.make_control({
				parent: $parent,
				df: { fieldtype: "Float", fieldname: "value", placeholder: placeholder || "", onchange: () => on_change(control.get_value()) },
				only_input: true,
				render_input: true,
			});
			if (flt(value)) control.set_input(flt(value));
			return control;
		}

		apply() {
			const calc = this.calc();
			if (calc.error) return frappe.msgprint(calc.error);
			if (calc.posting === null) return frappe.msgprint(__("Enter what you are buying: a qty and a UOM"));
			save_to_item(this.row.item_code, calc, this.info).then(() => {
				this.dialog.hide();
				apply_to_row(this.frm, this.cdt, this.cdn, calc, this.stock_uom, this.per_stock);
			});
		}
	}

	// --- Item master ----------------------------------------------------------------------------------

	// Add every level to the Item's UOM table; ask before changing a factor the Item already has.
	function save_to_item(item_code, calc, info) {
		const existing = Object.fromEntries((info.uoms || []).map((d) => [d.uom, flt(d.conversion_factor)]));
		const conflicts = calc.levels.filter((l, i) =>
			l.uom in existing && l.uom !== info.stock_uom
			&& Math.abs(existing[l.uom] - calc.factors[i]) > Math.pow(10, -CF_PRECISION) * calc.factors[i]
		);
		const save = (update) => frappe.call({
			method: METHOD + "save_item_uoms",
			args: { item_code, levels: JSON.stringify(level_json(calc)), update: JSON.stringify(update) },
		}).then((r) => {
			if (r.message && !r.message.saved) {
				frappe.show_alert({ message: __("UOMs not saved to Item: no permission"), indicator: "orange" });
			}
		});
		if (!conflicts.length) return save([]);
		const changes = conflicts.map((l) => __("{0} from {1} to {2}", [
			l.uom, fmt(existing[l.uom]), fmt(calc.factors[calc.levels.indexOf(l)]),
		]));
		return new Promise((resolve) => {
			frappe.confirm(
				__("Update {0} on Item {1}?", [changes.join(", "), item_code]),
				() => save(conflicts.map((l) => l.uom)).then(resolve),
				() => save([]).then(resolve)
			);
		});
	}

	// Only typed / Item Price prices are stored; suggested ones are not.
	function level_json(calc) {
		return calc.levels.map((l) => {
			const level = { uom: l.uom, qty: flt(l.qty) };
			if (l.inner && l.uom !== calc.stock_uom) Object.assign(level, { inner: l.inner, contains: flt(l.contains) });
			if (flt(l.rate) > 0) level.rate = flt(l.rate);
			if (flt(l.selling_price) > 0) level.selling_price = flt(l.selling_price);
			return level;
		});
	}

	// --- Transaction row ------------------------------------------------------------------------------

	function apply_to_row(frm, cdt, cdn, calc, stock_uom, per_stock) {
		const row = locals[cdt][cdn];
		const uom = calc.levels[calc.posting].uom;
		const cf = calc.factors[calc.posting];
		// Assign directly: ERPNext's uom handler would re-fetch the CF and the price list rate.
		row.uom = uom;
		row.conversion_factor = cf;
		row.qty = flt(calc.total / cf, precision("qty", row));
		row.uom_hierarchy = JSON.stringify({ stock_uom, levels: level_json(calc) });
		frm.cscript.conversion_factor(frm.doc, cdt, cdn, true); // stock_qty, stock UOM rate

		const posting = calc.levels[calc.posting];
		const selling = price_of(posting, "selling_price", cf, per_stock);
		if (selling && frappe.meta.has_field(cdt, "selling_price")) row.selling_price = flt(selling);
		const amount = amount_of(calc, per_stock);
		if (amount && row.qty) set_row_rate(frm, cdt, cdn, amount / row.qty);
		frm.cscript.calculate_taxes_and_totals();
		frm.refresh_field("items");
		frm.dirty();
		warn_whole_number(row, uom);
	}

	// The dialog price is the final price: no discount on top of it.
	function set_row_rate(frm, cdt, cdn, rate) {
		const row = locals[cdt][cdn];
		const field = rate_field(frm);
		const value = flt(rate, precision(field, row));
		if (field === "other_currency_rate") {
			frappe.model.set_value(cdt, cdn, field, value); // its handler converts it into Rate
			return;
		}
		row.price_list_rate = row.rate = value;
		row.discount_percentage = row.discount_amount = row.margin_rate_or_amount = 0;
		frm.cscript.calculate_stock_uom_rate && frm.cscript.calculate_stock_uom_rate(frm.doc, cdt, cdn);
	}

	function warn_whole_number(row, uom) {
		if (!(row.qty % 1)) return;
		frappe.db.get_value("UOM", uom, "must_be_whole_number").then((r) => {
			if (r.message && r.message.must_be_whole_number) {
				frappe.show_alert({ message: __("{0} must be a whole number: qty is {1}", [uom, row.qty]), indicator: "orange" });
			}
		});
	}

	// Waits for ERPNext's uom handler and the price-list call it starts from its callback.
	function after_erpnext(fn) {
		frappe.after_ajax(() => setTimeout(() => frappe.after_ajax(fn), 0));
	}

	// UOM changed in the grid on a row with levels: keep the stock qty (2 Carton -> 500 Nos).
	function on_uom_change(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		let saved = null;
		try {
			saved = row.uom_hierarchy ? JSON.parse(row.uom_hierarchy) : null;
		} catch (e) {
			return;
		}
		if (!saved || !row.uom || frm.doc.docstatus !== 0) return;
		saved.levels = with_stock(normalize(saved.levels || []), saved.stock_uom);
		const calc = calculate(saved.levels, saved.stock_uom);
		const i = calc.levels.findIndex((l) => l.uom === row.uom);
		const stock_qty = flt(row.stock_qty); // still the old value: ERPNext updates it after its server call
		if (calc.error || i < 0 || !stock_qty) return;
		const level = calc.levels[i];
		const cf = calc.factors[i];

		after_erpnext(() => {
			const r = locals[cdt][cdn];
			if (!r || r.uom !== level.uom) return;
			r.conversion_factor = cf;
			r.qty = flt(stock_qty / cf, precision("qty", r));
			saved.levels.forEach((l) => (l.qty = l.uom === level.uom ? r.qty : 0));
			r.uom_hierarchy = JSON.stringify(saved);
			frm.cscript.conversion_factor(frm.doc, cdt, cdn, true);
			if (flt(level.rate) > 0) set_row_rate(frm, cdt, cdn, level.rate);
			if (flt(level.selling_price) > 0 && frappe.meta.has_field(cdt, "selling_price")) {
				r.selling_price = flt(level.selling_price);
			}
			frm.cscript.calculate_taxes_and_totals();
			frm.refresh_field("items");
			warn_whole_number(r, level.uom);
		});
	}

	// doctype_js loads this file once per purchase doctype; register the handlers only once.
	ns.registered = ns.registered || {};
	CHILD_DOCTYPES.forEach((child) => {
		if (ns.registered[child]) return;
		ns.registered[child] = true;
		frappe.ui.form.on(child, { add_uom: open_dialog, uom: on_uom_change });
	});
})();
