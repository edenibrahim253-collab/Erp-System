import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today

from gps_erp.gps_tracking.setup_workflow import set_installation_status
from gps_erp.gps_tracking.utils import revert_installed_device

OPEN_ROLES = {"System Manager", "GPS Fleet Manager", "GPS Support Agent", "GPS Finance"}


class GPSInstallation(Document):
	"""Installation lifecycle:

	- Status moves only along the workflow graph (setup_workflow
	  .set_installation_status); a controller cannot jump states.
	- Submit requires a complete checklist with no Fail rows (Not Applicable
	  rows carry remarks), platform verification, and dates not in the future.
	- If a submitted assignment already covers this device/SIM for another
	  vehicle, submitting is blocked rather than duplicating truth.
	- Cancel cascades to the submitted QC inspections (their own cancel logic
	  rolls the status back) and reverts the device status this submission set.
	"""

	def validate(self):
		self.validate_dates()

	def before_submit(self):
		self.validate_checklist_complete()
		self.validate_assignment_consistency()

	def on_submit(self):
		set_installation_status(self.name, "Installed")
		if self.serial_no:
			frappe.db.set_value(
				"Serial No", self.serial_no, "gps_asset_status", "Installed", update_modified=False
			)

	def on_cancel(self):
		for name in frappe.get_all(
			"GPS Service Inspection",
			filters={"installation": self.name, "docstatus": 1},
			pluck="name",
		):
			frappe.get_doc("GPS Service Inspection", name).cancel()
		if self.serial_no:
			revert_installed_device(self.serial_no)

	def validate_dates(self):
		if self.scheduled_date and self.installation_date and self.installation_date < self.scheduled_date:
			frappe.throw(_("Installation Date cannot be before Scheduled Date."))
		if self.installation_date and getdate(self.installation_date) > getdate(today()):
			frappe.throw(_("Installation Date cannot be in the future."))

	def validate_checklist_complete(self):
		if not self.checklist:
			frappe.throw(_("Add at least one checklist item before submitting the installation."))
		for row in self.checklist:
			if not row.result:
				frappe.throw(_("Select a result for checklist item {0}.").format(frappe.bold(row.item)))
			if row.result == "Fail":
				frappe.throw(
					_("Checklist item {0} failed; resolve it or cancel this draft before another attempt.")
					.format(frappe.bold(row.item))
				)
			if row.result == "Not Applicable" and not (row.remarks or "").strip():
				frappe.throw(_("Add a remark explaining why {0} is not applicable.").format(frappe.bold(row.item)))
		if not self.platform_verified:
			frappe.throw(
				_("Confirm the device is active on the GPS platform before submitting the installation.")
			)

	def validate_assignment_consistency(self):
		assignment_vehicle = frappe.db.get_value(
			"GPS Device Assignment",
			{"serial_no": self.serial_no, "docstatus": 1, "status": "Active"},
			"vehicle",
		)
		if assignment_vehicle and assignment_vehicle != self.vehicle:
			frappe.throw(
				_("Device {0} is actively assigned to vehicle {1}; this installation names {2}.").format(
					self.serial_no, assignment_vehicle, self.vehicle
				)
			)
		if self.sim_card:
			sim_vehicle = frappe.db.get_value(
				"GPS SIM Assignment",
				{"sim_card": self.sim_card, "docstatus": 1, "status": "Active", "vehicle": ("is", "set")},
				"vehicle",
			)
			if sim_vehicle and sim_vehicle != self.vehicle:
				frappe.throw(
					_("SIM {0} is actively assigned to vehicle {1}; this installation names {2}.").format(
						self.sim_card, sim_vehicle, self.vehicle
					)
				)


def get_permission_query_conditions(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return ""

	roles = set(frappe.get_roles(user))
	if roles & OPEN_ROLES:
		return ""

	if "GPS Technician" in roles:
		employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
		condition = f"`tabGPS Installation`.`owner` = {frappe.db.escape(user)}"
		if employee:
			condition += f" or `tabGPS Installation`.`technician` = {frappe.db.escape(employee)}"
		return f"({condition})"

	return ""


def has_permission(doc, ptype=None, user=None):
	"""Row-level access. Returning False (not None) for a technician viewing
	someone else's record is required: None would fall through to the role's
	doctype-level permission and leak direct record access."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True

	roles = set(frappe.get_roles(user))
	if roles & OPEN_ROLES:
		return True

	if "GPS Technician" in roles:
		if ptype in ("cancel", "amend"):
			# corrections are a manager action; the doctype permission already
			# omits cancel/amend, this keeps the row hook from re-granting it
			return False
		employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
		if doc.owner == user:
			return True
		if employee and doc.technician == employee:
			return True
		return False

	return None
