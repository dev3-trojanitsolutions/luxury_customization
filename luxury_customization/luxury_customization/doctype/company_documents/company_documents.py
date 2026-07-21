# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class CompanyDocuments(Document):
	def before_save(self):
		if self.expiry_date and getdate(self.expiry_date) < getdate():
			self.status = "Expired"
		elif self.expiry_date:
			self.status = "Active"
