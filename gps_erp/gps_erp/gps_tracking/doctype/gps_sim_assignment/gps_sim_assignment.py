import frappe
from frappe import _
from frappe.model.document import Document

from gps_erp.gps_tracking.utils import ranges_overlap


class GPSSIMAssignment(Document):
	def validate(self):
		self.set_status()
		self.validate_dates()
		self.validate_no_overlap()

	def before_submit(self):
		self.validate_no_overlap()

	def on_submit(self):
		if frappe.db.get_value("GPS SIM Card", self.sim_card, "status") == "Reserved":
			frappe.db.set_value("GPS SIM Card", self.sim_card, "status", "Activated", update_modified=False)

	def on_cancel(self):
		frappe.db.set_value("GPS SIM Card", self.sim_card, "status", "Reserved", update_modified=False)

	def set_status(self):
		self.status = "Closed" if self.released_on else "Active"

	def validate_dates(self):
		if self.released_on and self.released_on < self.assigned_on:
			frappe.throw(_("Released On cannot be before Assigned On."))

	def validate_no_overlap(self):
		others = frappe.get_all(
			"GPS SIM Assignment",
			filters=[
				["sim_card", "=", self.sim_card],
				["name", "!=", self.name],
				["docstatus", "!=", 2],
			],
			fields=["name", "assigned_on", "released_on"],
		)
		for other in others:
			if ranges_overlap(self.assigned_on, self.released_on, other.assigned_on, other.released_on):
				frappe.throw(
					_(
						"SIM {0} is already covered by assignment {1} ({2} to {3}); overlapping assignments are not allowed."
					).format(
						self.sim_card,
						other.name,
						frappe.format(other.assigned_on, {"fieldtype": "Date"}),
						frappe.format(other.released_on, {"fieldtype": "Date"}) if other.released_on else _("open"),
					)
				)
