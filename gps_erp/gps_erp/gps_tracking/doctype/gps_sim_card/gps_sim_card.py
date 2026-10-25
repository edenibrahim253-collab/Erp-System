import re

import frappe
from frappe import _
from frappe.model.document import Document

ICCID_RE = re.compile(r"^\d{17,22}$")


class GPSSIMCard(Document):
	def autoname(self):
		self.normalize_identifiers()
		self.name = self.iccid

	def validate(self):
		self.normalize_identifiers()
		self.validate_iccid_format()
		self.validate_unique_msisdn()
		self.validate_dates()

	def normalize_identifiers(self):
		# Data (text) fields keep leading zeros; only strip separators.
		self.iccid = re.sub(r"[\s-]", "", str(self.iccid or ""))
		if self.msisdn:
			self.msisdn = re.sub(r"[\s-]", "", str(self.msisdn))

	def validate_iccid_format(self):
		if not ICCID_RE.match(self.iccid or ""):
			frappe.throw(
				_("ICCID {0} must be 17-22 digits (spaces and hyphens are stripped automatically).").format(
					frappe.bold(self.iccid)
				)
			)

	def validate_unique_msisdn(self):
		if not self.msisdn:
			return
		duplicate = frappe.db.get_value(
			"GPS SIM Card", {"msisdn": self.msisdn, "name": ("!=", self.name)}, "name"
		)
		if duplicate:
			frappe.throw(
				_("MSISDN {0} is already registered on SIM Card {1}").format(self.msisdn, duplicate),
				frappe.DuplicateEntryError,
			)

	def validate_dates(self):
		if self.activation_date and self.expiry_date and self.expiry_date < self.activation_date:
			frappe.throw(_("Expiry Date cannot be before Activation Date."))
