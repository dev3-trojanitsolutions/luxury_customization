import frappe
from erpnext.controllers.mapper import get_qty_already_mapped
from frappe.model.mapper import get_mapped_doc
from frappe.utils import flt


def get_direct_invoiced_qty(material_request):
	# Stock qty on non-cancelled Purchase Invoices made straight from this Material Request (no Purchase Order).
	# A Purchase Invoice updates the Material Request only with Update Stock, so count these here.
	rows = frappe.get_all(
		"Purchase Invoice Item",
		filters={"material_request": material_request, "docstatus": ["<", 2], "po_detail": ["is", "not set"]},
		fields=["material_request_item", "stock_qty"],
	)
	invoiced = frappe._dict()
	for row in rows:
		invoiced[row.material_request_item] = invoiced.get(row.material_request_item, 0) + flt(row.stock_qty)
	return invoiced


@frappe.whitelist()
def make_purchase_invoice(source_name, target_doc=None, args=None):
	# Same flow as ERPNext's material_request.make_purchase_order, with Purchase Invoice as the target.
	args = frappe.parse_json(args) if args else (frappe.flags.args or {})
	mapped_qty = get_qty_already_mapped(target_doc, "material_request_item", "stock_qty")
	invoiced_qty = get_direct_invoiced_qty(source_name)

	def pending_stock_qty(row):
		done = max(flt(row.ordered_qty) + flt(invoiced_qty.get(row.name)), flt(row.received_qty))
		return flt(row.stock_qty) - done - flt(mapped_qty.get(row.name))

	def select_item(row):
		selected = args.get("filtered_children") or []
		return pending_stock_qty(row) > 0 and (row.name in selected if selected else True)

	def update_item(source, target, source_parent):
		target.conversion_factor = flt(source.conversion_factor) or 1
		target.stock_qty = pending_stock_qty(source)
		target.qty = target.stock_qty / target.conversion_factor

	def postprocess(source, target):
		if args.get("supplier"):
			target.supplier = args.get("supplier")
		target.run_method("set_missing_values")
		target.run_method("calculate_taxes_and_totals")

	doclist = get_mapped_doc(
		"Material Request",
		source_name,
		{
			"Material Request": {
				"doctype": "Purchase Invoice",
				"validation": {"docstatus": ["=", 1], "material_request_type": ["=", "Purchase"]},
			},
			"Material Request Item": {
				"doctype": "Purchase Invoice Item",
				"field_map": [
					["name", "material_request_item"],
					["parent", "material_request"],
					["sales_order", "sales_order"],
					["sales_order_item", "sales_order_item"],
					["uom", "stock_uom"],
					["uom", "uom"],
				],
				"postprocess": update_item,
				"condition": select_item,
			},
		},
		target_doc,
		postprocess,
	)

	doclist.set_onload("load_after_mapping", False)
	return doclist
