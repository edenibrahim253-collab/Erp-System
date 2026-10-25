import frappe
from frappe import _
from frappe.model.document import Document

from gps_erp.gps_tracking.utils import ranges_overlap


class GPSDeviceAssignment(Document):
	def validate(self):
		self.set_status()
		self.validate_dates()
		self.validate_no_overlap()

	def before_submit(self):
		self.validate_no_overlap()

	def on_submit(self):
		frappe.db.set_value(
			"Serial No", self.serial_no, "gps_asset_status", "Assigned", update_modified=False
		)

	def on_cancel(self):
		frappe.db.set_value(
			"Serial No", self.serial_no, "gps_asset_status", "In Stock", update_modified=False
		)

	def set_status(self):
		self.status = "Closed" if self.returned_on else "Active"

	def validate_dates(self):
		if self.returned_on and self.returned_on < self.assigned_on:
			frappe.throw(_("Returned On cannot be before Assigned On."))

	def validate_no_overlap(self):
		others = frappe.get_all(
			"GPS Device Assignment",
			filters=[
				["serial_no", "=", self.serial_no],
				["name", "!=", self.name],
				["docstatus", "!=", 2],
			],
			fields=["name", "assigned_on", "returned_on"],
		)
		for other in others:
			if ranges_overlap(self.assigned_on, self.returned_on, other.assigned_on, other.returned_on):
				frappe.throw(
					_(
						"Device {0} is already covered by assignment {1} ({2} to {3}); overlapping assignments are not allowed."
					).format(
						self.serial_no,
						other.name,
						frappe.format(other.assigned_on, {"fieldtype": "Date"}),
						frappe.format(other.returned_on, {"fieldtype": "Date"}) if other.returned_on else _("open"),
					)
				)
