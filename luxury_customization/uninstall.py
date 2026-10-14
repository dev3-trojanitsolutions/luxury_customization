from luxury_customization.install import CUSTOM_FIELD_MODULES


def after_uninstall():
	for module in CUSTOM_FIELD_MODULES:
		module.delete_custom_fields()
