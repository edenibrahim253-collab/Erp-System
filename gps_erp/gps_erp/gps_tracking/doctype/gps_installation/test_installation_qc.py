import unittest

import frappe
from frappe.model.workflow import apply_workflow

from gps_erp.gps_tracking.doctype.gps_device_assignment.test_assignments import (
	make_fixture_data,
)
from gps_erp.gps_tracking.setup_workflow import (
	WORKFLOW_NAME,
	set_installation_status,
	sync_installation_workflow,
)

CHECKLIST = [
	{"item": "Device mounted securely", "result": "Pass"},
	{"item": "Power and ground connections", "result": "Pass"},
	{"item": "Antenna placement", "result": "Pass"},
]


class TestGPSInstallationQC(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.fixture = make_fixture_data()
		cls.created = cls.fixture["created"]
		cls.created_docs = []
		cls.created_assignments = []
		cls.qc_procedure_existed = frappe.db.exists("Quality Procedure", "GPS Installation Quality Check")
		sync_installation_workflow()
		# controller-side status logic is exercised directly here; the dedicated
		# workflow test re-enables the workflow itself.
		cls.original_workflow_active = frappe.db.get_value("Workflow", WORKFLOW_NAME, "is_active")
		frappe.db.set_value("Workflow", WORKFLOW_NAME, "is_active", 0, update_modified=False)

	@classmethod
	def tearDownClass(cls):
		for doctype, name in reversed(cls.created_docs):
			if not frappe.db.exists(doctype, name):
				continue
			if doctype == "User":
				frappe.delete_doc(doctype, name, force=True, ignore_missing=True)
				continue
			doc = frappe.get_doc(doctype, name)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc(doctype, name, force=True, ignore_missing=True)
		if not cls.qc_procedure_existed:
			frappe.delete_doc(
				"Quality Procedure", "GPS Installation Quality Check", force=True, ignore_missing=True
			)
		for name in (cls.fixture["serial"], cls.fixture["serial2"]):
			frappe.db.set_value("Serial No", name, "gps_asset_status", "In Stock", update_modified=False)
			frappe.delete_doc("Serial No", name, force=True, ignore_missing=True)
		for name in (cls.fixture["sim"], cls.fixture["sim2"]):
			frappe.delete_doc("GPS SIM Card", name, force=True, ignore_missing=True)
		frappe.delete_doc("GPS Vehicle", cls.fixture["vehicle"], force=True, ignore_missing=True)
		if cls.created.get("customer"):
			frappe.delete_doc("Customer", cls.fixture["customer"], force=True, ignore_missing=True)
		if cls.created.get("item"):
			frappe.delete_doc("Item", "_Test GPS Tracker", force=True, ignore_missing=True)
		if cls.created.get("customer_group"):
			frappe.delete_doc("Customer Group", "_Test GPS Fleet", force=True, ignore_missing=True)
		if cls.original_workflow_active is not None:
			frappe.db.set_value(
				"Workflow", WORKFLOW_NAME, "is_active", cls.original_workflow_active, update_modified=False
			)

	def track(self, doctype, name):
		self.created_docs.append((doctype, name))

	def make_installation(self, checklist=None, platform_verified=1, submit=False, **kwargs):
		values = {
			"doctype": "GPS Installation",
			"vehicle": self.fixture["vehicle"],
			"serial_no": self.fixture["serial"],
			"sim_card": self.fixture["sim"],
			"scheduled_date": "2026-01-01",
			"installation_date": "2026-01-02",
			"platform_verified": platform_verified,
			"checklist": [dict(row) for row in (CHECKLIST if checklist is None else checklist)],
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		self.track("GPS Installation", doc.name)
		if submit:
			doc.submit()
		return doc

	def make_qc_ready_installation(self):
		"""Submitted installation parked in Awaiting QC, as the workflow requires."""
		installation = self.make_installation(submit=True)
		set_installation_status(installation.name, "Awaiting QC")
		return installation

	def make_device_assignment(self, **kwargs):
		values = {
			"doctype": "GPS Device Assignment",
			"serial_no": self.fixture["serial"],
			"vehicle": self.fixture["vehicle"],
			"assigned_on": "2026-01-01",
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		doc.submit()
		self.created_assignments.append(doc.name)
		return doc

	def make_inspection(self, installation, result="Pass", findings=None):
		doc = frappe.get_doc(
			{
				"doctype": "GPS Service Inspection",
				"installation": installation.name,
				"result": result,
				"findings": findings,
				"inspection_date": "2026-01-03",
			}
		)
		doc.insert(ignore_permissions=True)
		self.track("GPS Service Inspection", doc.name)
		return doc

	def make_user(self, email, role):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		)
		user.insert(ignore_permissions=True)
		self.track("User", user.name)
		return user.name

	def delete_doc(self, doctype, name):
		if (doctype, name) in self.created_docs:
			self.created_docs.remove((doctype, name))
		doc = frappe.get_doc(doctype, name) if frappe.db.exists(doctype, name) else None
		if doc is not None and doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc(doctype, name, force=True, ignore_missing=True)

	def status_of(self, installation):
		return frappe.db.get_value("GPS Installation", installation.name, "status")

	# --- workflow definition and migration safety ---

	def test_workflow_exists_state_field_and_states(self):
		workflow = frappe.get_doc("Workflow", WORKFLOW_NAME)
		self.assertEqual(workflow.document_type, "GPS Installation")
		self.assertEqual(workflow.workflow_state_field, "status")
		self.assertEqual(len(workflow.states), 7)
		self.assertGreaterEqual(len(workflow.transitions), 7)

	def test_sync_is_idempotent_and_keeps_admin_disable(self):
		sync_installation_workflow()
		workflow = frappe.get_doc("Workflow", WORKFLOW_NAME)
		self.assertEqual(workflow.is_active, 0)  # sync never re-enables
		saved_modified = frappe.db.get_value("Workflow", WORKFLOW_NAME, "modified")
		sync_installation_workflow()
		self.assertEqual(
			frappe.db.get_value("Workflow", WORKFLOW_NAME, "modified"), saved_modified
		)

	def test_workflow_transition_updates_status_field(self):
		tech = self.make_user("_test.tech.trans@gps-erp.example", "GPS Technician")
		installation = self.make_installation()
		frappe.db.set_value("GPS Installation", installation.name, "owner", tech, update_modified=False)
		workflow = frappe.get_doc("Workflow", WORKFLOW_NAME)
		workflow.db_set("is_active", 1)
		frappe.clear_cache()  # workflow lookups are cached per doctype
		frappe.set_user(tech)
		try:
			installation.reload()
			self.assertEqual(installation.status, "Pending")
			apply_workflow(installation, "Start Work")
			self.assertEqual(
				frappe.db.get_value("GPS Installation", installation.name, "status"), "In Progress"
			)
		finally:
			frappe.set_user("Administrator")
			workflow.db_set("is_active", 0)
			frappe.clear_cache()

	# --- submission guards ---

	def test_submit_requires_checklist(self):
		doc = self.make_installation(checklist=[])
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		self.delete_doc("GPS Installation", doc.name)

	def test_submit_requires_result_on_every_row(self):
		doc = self.make_installation(checklist=[{"item": "Wiring", "result": ""}])
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		self.delete_doc("GPS Installation", doc.name)

	def test_submit_blocked_by_failed_checklist_row(self):
		doc = self.make_installation(
			checklist=[{"item": "Antenna placement", "result": "Fail", "remarks": "Damaged cable."}]
		)
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		self.delete_doc("GPS Installation", doc.name)

	def test_not_applicable_row_requires_remark(self):
		doc = self.make_installation(checklist=[{"item": "Antenna", "result": "Not Applicable"}])
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		# a rejected submit leaves msgprint state behind; without clearing it
		# the next save's check_if_latest re-raises it as a timestamp mismatch
		frappe.local.message_log = []
		frappe.local.debug_message_log = []
		doc.reload()
		doc.checklist[0].remarks = "Vehicle has built-in antenna."
		doc.save()
		doc.submit()
		self.assertEqual(self.status_of(doc), "Installed")
		self.delete_doc("GPS Installation", doc.name)

	def test_submit_requires_platform_verification(self):
		doc = self.make_installation(platform_verified=0)
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		self.delete_doc("GPS Installation", doc.name)

	def test_future_installation_date_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_installation(scheduled_date="2030-01-01", installation_date="2030-06-01")

	def test_installation_date_before_scheduled_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_installation(scheduled_date="2026-01-05", installation_date="2026-01-02")

	def test_submit_sets_installed(self):
		doc = self.make_installation(submit=True)
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(self.status_of(doc), "Installed")
		self.assertEqual(
			frappe.db.get_value("Serial No", self.fixture["serial"], "gps_asset_status"), "Installed"
		)
		self.delete_doc("GPS Installation", doc.name)

	# --- assignment integration ---

	def test_submit_blocked_when_device_assigned_elsewhere(self):
		other_vehicle = frappe.get_doc(
			{"doctype": "GPS Vehicle", "license_plate": "ASTR", "customer": self.fixture["customer"]}
		)
		other_vehicle.insert(ignore_permissions=True)
		self.track("GPS Vehicle", other_vehicle.name)
		self.make_device_assignment(vehicle=other_vehicle.name)
		doc = self.make_installation()
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		self.delete_doc("GPS Installation", doc.name)
		for name in self.created_assignments:
			a = frappe.get_doc("GPS Device Assignment", name)
			if a.docstatus == 1:
				a.cancel()
			self.created_assignments.remove(name)
			frappe.delete_doc("GPS Device Assignment", name, force=True, ignore_missing=True)

	# --- QC lifecycle ---

	def test_inspection_rejected_before_send_to_qc(self):
		# submitted but still Installed (never moved to Awaiting QC)
		installation = self.make_installation(submit=True)
		with self.assertRaises(frappe.ValidationError):
			self.make_inspection(installation)

	def test_inspection_rejected_on_draft_installation(self):
		installation = self.make_installation()
		with self.assertRaises(frappe.ValidationError):
			self.make_inspection(installation)

	def test_qc_pass_updates_installation(self):
		installation = self.make_qc_ready_installation()
		doc = self.make_inspection(installation, result="Pass")
		doc.submit()
		self.assertEqual(self.status_of(installation), "QC Passed")

	def test_qc_fail_creates_non_conformance(self):
		installation = self.make_qc_ready_installation()
		doc = self.make_inspection(
			installation, result="Fail", findings="Loose antenna, device offline on platform."
		)
		doc.submit()
		self.assertTrue(doc.non_conformance)
		self.track("Non Conformance", doc.non_conformance)
		self.assertEqual(
			frappe.db.get_value("Non Conformance", doc.non_conformance, "status"), "Open"
		)
		self.assertEqual(self.status_of(installation), "QC Failed")

	def test_qc_fail_requires_findings(self):
		installation = self.make_qc_ready_installation()
		with self.assertRaises(frappe.ValidationError):
			self.make_inspection(installation, result="Fail").submit()

	def test_repeat_fail_reuses_open_non_conformance(self):
		installation = self.make_qc_ready_installation()
		first = self.make_inspection(installation, result="Fail", findings="Antenna loose.")
		first.submit()
		self.track("Non Conformance", first.non_conformance)
		# rework, then a second failed inspection
		set_installation_status(installation.name, "Installed", correction=True)
		set_installation_status(installation.name, "Awaiting QC")
		second = self.make_inspection(installation, result="Fail", findings="Antenna still loose.")
		second.submit()
		self.assertEqual(second.non_conformance, first.non_conformance)

	def test_full_rework_cycle_preserves_history(self):
		installation = self.make_qc_ready_installation()
		fail_doc = self.make_inspection(installation, result="Fail", findings="Offline after install.")
		fail_doc.submit()
		self.track("Non Conformance", fail_doc.non_conformance)
		self.assertEqual(self.status_of(installation), "QC Failed")
		# Rework Done + Send to QC, then the re-inspection passes
		set_installation_status(installation.name, "Installed", correction=True)
		set_installation_status(installation.name, "Awaiting QC")
		pass_doc = self.make_inspection(installation, result="Pass")
		pass_doc.submit()
		self.assertEqual(self.status_of(installation), "QC Passed")
		# audit history: both inspections still submitted and pointing at the installation
		self.assertEqual(frappe.db.get_value("GPS Service Inspection", fail_doc.name, "docstatus"), 1)
		self.assertEqual(frappe.db.get_value("GPS Service Inspection", pass_doc.name, "docstatus"), 1)

	def test_cancel_pass_inspection_recomputes_to_installed(self):
		installation = self.make_qc_ready_installation()
		doc = self.make_inspection(installation, result="Pass")
		doc.submit()
		doc.cancel()
		self.assertEqual(self.status_of(installation), "Installed")

	def test_cancel_latest_inspection_falls_back_to_previous_result(self):
		installation = self.make_qc_ready_installation()
		fail_doc = self.make_inspection(installation, result="Fail", findings="Offline on platform.")
		fail_doc.submit()
		self.track("Non Conformance", fail_doc.non_conformance)
		set_installation_status(installation.name, "Installed", correction=True)
		set_installation_status(installation.name, "Awaiting QC")
		pass_doc = self.make_inspection(installation, result="Pass")
		pass_doc.submit()
		self.assertEqual(self.status_of(installation), "QC Passed")
		pass_doc.cancel()
		self.assertEqual(self.status_of(installation), "QC Failed")

	# --- cancellation cascades and status gateway ---

	def test_status_gateway_blocks_invalid_jumps(self):
		installation = self.make_installation(submit=True)
		with self.assertRaises(frappe.ValidationError):
			set_installation_status(installation.name, "QC Passed")
		with self.assertRaises(frappe.ValidationError):
			set_installation_status(installation.name, "Closed")
		# corrections are only allowed when flagged as such
		set_installation_status(installation.name, "Awaiting QC")
		set_installation_status(installation.name, "QC Passed")
		set_installation_status(installation.name, "Installed", correction=True)
		self.assertEqual(self.status_of(installation), "Installed")
		self.delete_doc("GPS Installation", installation.name)

	def test_cancel_installation_cascades_and_reverts_device(self):
		self.make_device_assignment()  # serial -> vehicle, device becomes Assigned
		installation = self.make_qc_ready_installation()
		doc = self.make_inspection(installation, result="Pass")
		doc.submit()
		self.assertEqual(self.status_of(installation), "QC Passed")
		self.assertEqual(
			frappe.db.get_value("Serial No", self.fixture["serial"], "gps_asset_status"), "Installed"
		)
		installation.cancel()
		self.assertEqual(frappe.db.get_value("GPS Service Inspection", doc.name, "docstatus"), 2)
		# device falls back to what the still-submitted assignment says
		self.assertEqual(
			frappe.db.get_value("Serial No", self.fixture["serial"], "gps_asset_status"), "Assigned"
		)
		for name in self.created_assignments:
			a = frappe.get_doc("GPS Device Assignment", name)
			if a.docstatus == 1:
				a.cancel()
			self.created_assignments.remove(name)
			frappe.delete_doc("GPS Device Assignment", name, force=True, ignore_missing=True)
		self.assertEqual(
			frappe.db.get_value("Serial No", self.fixture["serial"], "gps_asset_status"), "In Stock"
		)

	# --- permissions ---

	def test_technician_can_submit_others_cannot(self):
		tech = self.make_user("_test.tech.submit@gps-erp.example", "GPS Technician")
		other = self.make_user("_test.tech.other@gps-erp.example", "GPS Technician")
		doc = self.make_installation()
		frappe.db.set_value("GPS Installation", doc.name, "owner", tech, update_modified=False)
		self.assertTrue(
			frappe.has_permission("GPS Installation", ptype="submit", doc=doc.name, user=tech)
		)
		self.assertFalse(
			frappe.has_permission("GPS Installation", ptype="submit", doc=doc.name, user=other)
		)
		self.assertFalse(
			frappe.has_permission("GPS Installation", ptype="cancel", doc=doc.name, user=tech)
		)

	def test_technician_row_security(self):
		tech_a = self.make_user("_test.tech.a@gps-erp.example", "GPS Technician")
		tech_b = self.make_user("_test.tech.b@gps-erp.example", "GPS Technician")
		manager = self.make_user("_test.fleet.mgr@gps-erp.example", "GPS Fleet Manager")
		stranger = self.make_user("_test.nobody@gps-erp.example", "Guest")

		doc_a = self.make_installation()
		doc_b = self.make_installation()
		frappe.db.set_value("GPS Installation", doc_a.name, "owner", tech_a, update_modified=False)
		frappe.db.set_value("GPS Installation", doc_b.name, "owner", tech_b, update_modified=False)

		frappe.set_user(tech_a)
		try:
			visible = frappe.get_list(
				"GPS Installation", filters={"name": ("in", [doc_a.name, doc_b.name])}, pluck="name"
			)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(sorted(visible), [doc_a.name])
		self.assertTrue(frappe.has_permission("GPS Installation", ptype="read", doc=doc_a.name, user=tech_a))
		self.assertFalse(
			frappe.has_permission("GPS Installation", ptype="read", doc=doc_b.name, user=tech_a)
		)

		frappe.set_user(manager)
		try:
			visible_mgr = frappe.get_list(
				"GPS Installation", filters={"name": ("in", [doc_a.name, doc_b.name])}, pluck="name"
			)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(sorted(visible_mgr), sorted([doc_a.name, doc_b.name]))

		self.assertFalse(
			frappe.has_permission("GPS Installation", ptype="read", doc=doc_a.name, user=stranger)
		)
