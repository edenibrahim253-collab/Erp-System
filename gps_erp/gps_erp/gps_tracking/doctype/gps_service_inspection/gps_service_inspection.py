import frappe
from frappe import _
from frappe.model.document import Document

QC_PROCEDURE = "GPS Installation Quality Check"


class GPSServiceInspection(Document):
	def validate(self):
		self.validate_installation()
		if self.result == "Fail" and not (self.findings or "").strip():
			frappe.throw(_("Describe the findings when the inspection fails."))

	def validate_installation(self):
		status = frappe.db.get_value("GPS Installation", self.installation, "status")
		if status not in ("Installed", "Awaiting QC", "QC Failed"):
			frappe.throw(
				_("Inspections can only be recorded for installations awaiting or failing QC (current status: {0}).").format(
					status
				)
			)

	def on_submit(self):
		if self.result == "Pass":
			frappe.db.set_value("GPS Installation", self.installation, "status", "QC Passed", update_modified=False)
			if self.serial_no:
				frappe.db.set_value("Serial No", self.serial_no, "gps_asset_status", "Installed", update_modified=False)
		else:
			nc = self.create_non_conformance()
			self.db_set("non_conformance", nc.name, update_modified=False)
			frappe.db.set_value("GPS Installation", self.installation, "status", "QC Failed", update_modified=False)

	def on_cancel(self):
		if frappe.db.exists("GPS Installation", self.installation):
			frappe.db.set_value("GPS Installation", self.installation, "status", "Awaiting QC", update_modified=False)

	def create_non_conformance(self):
		procedure = frappe.db.get_value("Quality Procedure", QC_PROCEDURE, "name")
		if not procedure:
			procedure = frappe.get_doc(
				{"doctype": "Quality Procedure", "quality_procedure_name": QC_PROCEDURE}
			).insert(ignore_permissions=True).name

		installation_label = _("GPS Installation {0}").format(self.installation)
		nc = frappe.get_doc(
			{
				"doctype": "Non Conformance",
				"subject": _("QC failed: {0}").format(installation_label),
				"procedure": procedure,
				"status": "Open",
			}
		)
		if frappe.get_meta("Non Conformance").has_field("content"):
			nc.set("content", self.findings)
		if frappe.get_meta("Non Conformance").has_field("customer"):
			customer = frappe.db.get_value("GPS Installation", self.installation, "customer")
			if customer:
				nc.set("customer", customer)
		nc.insert(ignore_permissions=True)
		return nc
