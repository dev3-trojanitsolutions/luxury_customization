import json

import frappe
from frappe.model.utils.user_settings import sync_user_settings

GRIDS = {
	"Purchase Order": "Purchase Order Item",
	"Purchase Receipt": "Purchase Receipt Item",
	"Purchase Invoice": "Purchase Invoice Item",
	"Supplier Quotation": "Supplier Quotation Item",
}
NEW_COLUMN = "add_uom"


def execute():
	# Saved "Configure Columns" layouts replace in_list_view, so the "+ UOM" button would not show
	# for those users. Add it right after the UOM column (or after Qty when UOM is not shown).
	sync_user_settings()
	for doctype, child in GRIDS.items():
		rows = frappe.db.sql("select user, data from `__UserSettings` where doctype=%s", (doctype,), as_dict=True)
		for row in rows:
			data = json.loads(row.data or "{}")
			columns = (data.get("GridView") or {}).get(child)
			if not columns or any(c.get("fieldname") == NEW_COLUMN for c in columns):
				continue
			anchor = next(
				(i for name in ("uom", "qty") for i, c in enumerate(columns) if c.get("fieldname") == name),
				len(columns) - 1,
			)
			columns.insert(anchor + 1, {"fieldname": NEW_COLUMN, "columns": 1})
			frappe.db.sql(
				"update `__UserSettings` set data=%s where user=%s and doctype=%s",
				(json.dumps(data), row.user, doctype),
			)
			frappe.cache.hdel("_user_settings", f"{doctype}::{row.user}")
