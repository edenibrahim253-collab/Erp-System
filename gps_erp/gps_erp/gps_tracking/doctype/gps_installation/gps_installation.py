import frappe
from frappe import _
from frappe.model.document import Document

OPEN_ROLES = {"System Manager", "GPS Fleet Manager", "GPS Support Agent", "GPS Finance"}


class GPSInstallation(Document):
	def validate(self):
		self.validate_dates()

	def before_submit(self):
		self.validate_checklist_complete()
		self.validate_platform_verified()

	def on_submit(self):
		if self.status in ("Pending", "In Progress"):
			self.db_set("status", "Installed", update_modified=False)
		if self.serial_no:
			frappe.db.set_value(
				"Serial No", self.serial_no, "gps_asset_status", "Installed", update_modified=False
			)

	def validate_dates(self):
		if self.scheduled_date and self.installation_date and self.installation_date < self.scheduled_date:
			frappe.throw(_("Installation Date cannot be before Scheduled Date."))

	def validate_checklist_complete(self):
		if not self.checklist:
			frappe.throw(_("Add at least one checklist item before submitting the installation."))
		for row in self.checklist:
			if not row.result:
				frappe.throw(_("Select a result for checklist item {0}.").format(frappe.bold(row.item)))

	def validate_platform_verified(self):
		if not self.platform_verified:
			frappe.throw(
				_("Confirm the device is active on the GPS platform before submitting the installation.")
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
	user = user or frappe.session.user
	if user == "Administrator":
		return True

	roles = set(frappe.get_roles(user))
	if roles & OPEN_ROLES:
		return True

	if "GPS Technician" in roles:
		employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
		return doc.owner == user or (employee and doc.technician == employee)

	return None
