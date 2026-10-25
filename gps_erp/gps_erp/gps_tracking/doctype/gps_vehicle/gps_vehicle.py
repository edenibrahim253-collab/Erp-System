import frappe
from frappe import _
from frappe.model.document import Document


class GPSVehicle(Document):
	def autoname(self):
		self.normalize_identifiers()
		self.name = self.license_plate

	def validate(self):
		self.normalize_identifiers()
		self.validate_unique_vin()

	def normalize_identifiers(self):
		self.license_plate = "".join((self.license_plate or "").upper().split())
		if self.vin_chassis:
			self.vin_chassis = "".join(self.vin_chassis.upper().split())

	def validate_unique_vin(self):
		if not self.vin_chassis:
			return
		duplicate = frappe.db.get_value(
			"GPS Vehicle",
			{"vin_chassis": self.vin_chassis, "name": ("!=", self.name)},
			"name",
		)
		if duplicate:
			frappe.throw(
				_("VIN / Chassis No {0} is already registered on Vehicle {1}").format(
					self.vin_chassis, duplicate
				),
				frappe.DuplicateEntryError,
			)
