import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today

from gps_erp.gps_tracking.utils import ranges_overlap


class GPSSIMAssignment(Document):
	"""Lifecycle rules:
	- Active = no released_on; Closed = released_on set (future dates rejected).
	- Overlap checks run against every non-cancelled record, drafts included,
	  so a draft already reserves the date range for the SIM.
	- Only a submitted Active assignment flips a Reserved SIM to Activated.
	- Cancel reverts to Reserved only when the SIM still reads Activated
	  (not Blocked/Retired/...) and no other submitted Active assignment
	  covers it.
	"""

	def validate(self):
		self.set_status()
		self.validate_dates()
		self.validate_no_overlap()

	def before_submit(self):
		self.validate_no_overlap()

	def on_submit(self):
		# Only an Active assignment activates a card, and only from Reserved;
		# Deactivated/Blocked/Retired cards keep their operational status.
		if (
			self.status == "Active"
			and frappe.db.get_value("GPS SIM Card", self.sim_card, "status") == "Reserved"
		):
			frappe.db.set_value("GPS SIM Card", self.sim_card, "status", "Activated", update_modified=False)

	def on_cancel(self):
		# Only undo a status this kind of assignment could have set, and only if
		# no other submitted assignment still covers the SIM.
		if frappe.db.get_value("GPS SIM Card", self.sim_card, "status") != "Activated":
			return
		if not self.has_open_assignment():
			frappe.db.set_value("GPS SIM Card", self.sim_card, "status", "Reserved", update_modified=False)

	def set_status(self):
		self.status = "Closed" if self.released_on else "Active"

	def validate_dates(self):
		if self.released_on and self.released_on < self.assigned_on:
			frappe.throw(_("Released On cannot be before Assigned On."))
		if self.released_on and getdate(self.released_on) > getdate(today()):
			frappe.throw(_("Released On cannot be in the future; close the assignment when released."))

	def has_open_assignment(self):
		return frappe.db.exists(
			"GPS SIM Assignment",
			{
				"sim_card": self.sim_card,
				"status": "Active",
				"docstatus": 1,
				"name": ("!=", self.name),
			},
		)

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
