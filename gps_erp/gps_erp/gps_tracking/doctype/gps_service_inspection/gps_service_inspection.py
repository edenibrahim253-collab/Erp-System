import frappe
from frappe import _
from frappe.model.document import Document

from gps_erp.gps_tracking.setup_workflow import set_installation_status

QC_PROCEDURE = "GPS Installation Quality Check"


class GPSServiceInspection(Document):
	"""QC rules:
	- Inspections may only be recorded against a submitted installation in
	  Awaiting QC; the manager sends it there with the "Send to QC" workflow
	  action, so QC cannot bypass the workflow graph.
	- Pass/Fail moves the installation along the Pass QC / Fail QC transitions
	  (setup_workflow.set_installation_status), never by a direct jump.
	- A failed inspection links to one open Non Conformance per installation:
	  repeated failures while an NC is Open reuse it; a new NC is raised only
	  when none is open. Cancelling an inspection does not close the NC.
	- Cancelling recomputes the installation status from the newest remaining
	  submitted inspection (Installed when none is left); every inspection
	  document stays in the history untouched.
	"""

	def validate(self):
		self.validate_installation()
		if self.result == "Fail" and not (self.findings or "").strip():
			frappe.throw(_("Describe the findings when the inspection fails."))

	def validate_installation(self):
		installation = frappe.db.get_value(
			"GPS Installation", self.installation, ["status", "docstatus"], as_dict=True
		)
		if not installation or installation.docstatus != 1 or installation.status != "Awaiting QC":
			frappe.throw(
				_(
					"Inspections can only be recorded for submitted installations in Awaiting QC (current status: {0})."
				).format(installation.status if installation else None)
			)

	def on_submit(self):
		if self.result == "Pass":
			set_installation_status(self.installation, "QC Passed")
			if self.serial_no:
				frappe.db.set_value("Serial No", self.serial_no, "gps_asset_status", "Installed", update_modified=False)
		else:
			nc = self.create_non_conformance()
			self.db_set("non_conformance", nc.name, update_modified=False)
			set_installation_status(self.installation, "QC Failed")

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
		set_installation_status(self.installation, status, correction=True)

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
