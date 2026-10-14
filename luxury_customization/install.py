from luxury_customization.customizations import (
	company,
	employee,
	employee_checkin,
	purchase_invoice,
	purchase_order,
	purchase_receipt,
	rate_precision,
	supplier_quotation,
	item_price
)

CUSTOM_FIELD_MODULES = [
	employee,
	company,
	employee_checkin,
	purchase_order,
	purchase_receipt,
	purchase_invoice,
	supplier_quotation,
	item_price
]


def after_install():
	setup_customizations()


def after_migrate():
	setup_customizations()


def setup_customizations():
	for module in CUSTOM_FIELD_MODULES:
		module.create_custom_fields()
	rate_precision.set_rate_precision()
