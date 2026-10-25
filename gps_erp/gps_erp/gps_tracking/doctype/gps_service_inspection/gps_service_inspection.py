import frappe
from frappe import _
from frappe.model.document import Document

QC_PROCEDURE = "GPS Installation Quality Check"


class GPSServiceInspection(Document):
	"""QC rules:
	- Inspections may only be recorded while the installation is Installed,
	  Awaiting QC or QC Failed (re-inspection after rework).
	- A failed inspection links to one open Non Conformance per installation:
	  repeated failures while an NC is Open reuse it; a new NC is raised only
	  when none is open. Cancelling an inspection does not close the NC.
	- Cancelling recomputes the installation status from the newest remaining
	  submitted inspection (Installed when none is left).
	"""

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
		if not frappe.db.exists("GPS Installation", self.installation):
			return
		remaining = frappe.db.sql(
			"""SELECT result FROM `tabGPS Service Inspection`
			WHERE installation = %s AND docstatus = 1 AND name != %s
			ORDER BY inspection_date DESC, creation DESC LIMIT 1""",
			(self.installation, self.name),
			pluck="result",
		)
		if remaining:
			status = "QC Passed" if remaining[0] == "Pass" else "QC Failed"
		else:
			status = "Installed"
		frappe.db.set_value("GPS Installation", self.installation, "status", status, update_modified=False)

	def create_non_conformance(self):
		open_nc = frappe.db.sql(
			"""SELECT i.non_conformance FROM `tabGPS Service Inspection` i
			INNER JOIN `tabNon Conformance` n ON n.name = i.non_conformance
			WHERE i.installation = %s AND i.docstatus = 1 AND i.name != %s
			AND i.non_conformance IS NOT NULL AND i.non_conformance != ''
			AND n.status = 'Open'
			ORDER BY i.creation DESC LIMIT 1""",
			(self.installation, self.name),
		)
		if open_nc:
			return frappe.get_doc("Non Conformance", open_nc[0][0])

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
