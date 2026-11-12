import json

import frappe
from frappe.model.utils.user_settings import clear_user_settings_cache, sync_user_settings

GRIDS = {
	"Purchase Order": "Purchase Order Item",
	"Purchase Receipt": "Purchase Receipt Item",
	"Purchase Invoice": "Purchase Invoice Item",
}
NEW_COLUMNS = ["previous_selling_price", "selling_price"]


def execute():
	# Saved "Configure Columns" layouts replace in_list_view, so new fields never show for those users.
	# Add the selling price columns to each saved items-table layout, after Buying Rate or Rate.
	sync_user_settings()  # cache can be newer than the table
	for doctype, child in GRIDS.items():
		rows = frappe.db.sql(
			"select user, data from `__UserSettings` where doctype=%s", (doctype,), as_dict=True
		)
		for row in rows:
			data = json.loads(row.data or "{}")
			columns = (data.get("GridView") or {}).get(child)
			if not columns or not add_columns(columns):
				continue
			frappe.db.sql(
				"update `__UserSettings` set data=%s where user=%s and doctype=%s",
				(json.dumps(data), row.user, doctype),
			)
		clear_user_settings_cache(doctype)


def add_columns(columns):
	present = {c.get("fieldname") for c in columns}
	missing = [{"fieldname": f, "columns": 1} for f in NEW_COLUMNS if f not in present]
	if not missing:
		return False
	anchor = next(
		(i for name in ("other_currency_rate", "rate") for i, c in enumerate(columns) if c.get("fieldname") == name),
		len(columns) - 1,
	)
	columns[anchor + 1 : anchor + 1] = missing
	return True
