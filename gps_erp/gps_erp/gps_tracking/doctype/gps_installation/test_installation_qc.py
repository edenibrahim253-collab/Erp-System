import unittest

import frappe

from gps_erp.gps_tracking.doctype.gps_device_assignment.test_assignments import (
	make_fixture_data,
)

WORKFLOW_NAME = "GPS Installation Workflow"

CHECKLIST = [
	{"item": "Device mounted securely", "result": "Pass"},
	{"item": "Power and ground connections", "result": "Pass"},
	{"item": "Antenna placement", "result": "Pass"},
]


def make_installation(fixture, checklist=None, platform_verified=1, submit=False):
	doc = frappe.get_doc(
		{
			"doctype": "GPS Installation",
			"vehicle": fixture["vehicle"],
			"serial_no": fixture["serial"],
			"sim_card": fixture["sim"],
			"scheduled_date": "2026-01-01",
			"installation_date": "2026-01-02",
			"platform_verified": platform_verified,
			"checklist": (CHECKLIST if checklist is None else checklist)
			and [dict(row) for row in (CHECKLIST if checklist is None else checklist)],
		}
	)
	doc.insert(ignore_permissions=True)
	if submit:
		doc.submit()
	return doc


def make_inspection(installation, result="Pass", findings=None):
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
	return doc


class TestGPSInstallationQC(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.fixture = make_fixture_data()
		# submit flow is tested directly; keep the workflow inactive meanwhile
		if frappe.db.exists("Workflow", WORKFLOW_NAME):
			workflow = frappe.get_doc("Workflow", WORKFLOW_NAME)
			workflow.set("is_active", 0)
			workflow.save(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		for docname in frappe.get_all("GPS Service Inspection", pluck="name"):
			if frappe.db.get_value("GPS Service Inspection", docname, "docstatus") == 1:
				frappe.get_doc("GPS Service Inspection", docname).cancel()
			frappe.delete_doc("GPS Service Inspection", docname, force=True, ignore_missing=True)
		for docname in frappe.get_all("Non Conformance", pluck="name"):
			frappe.delete_doc("Non Conformance", docname, force=True, ignore_missing=True)
		for docname in frappe.get_all("GPS Installation", pluck="name"):
			if frappe.db.get_value("GPS Installation", docname, "docstatus") == 1:
				frappe.get_doc("GPS Installation", docname).cancel()
			frappe.delete_doc("GPS Installation", docname, force=True, ignore_missing=True)
		frappe.delete_doc("Serial No", cls.fixture["serial"], force=True, ignore_missing=True)
		frappe.delete_doc("GPS SIM Card", cls.fixture["sim"], force=True, ignore_missing=True)
		frappe.delete_doc("GPS Vehicle", cls.fixture["vehicle"], force=True, ignore_missing=True)
		if frappe.db.exists("Workflow", WORKFLOW_NAME):
			workflow = frappe.get_doc("Workflow", WORKFLOW_NAME)
			workflow.set("is_active", 1)
			workflow.save(ignore_permissions=True)

	def test_workflow_exists_and_active_states(self):
		workflow = frappe.get_doc("Workflow", WORKFLOW_NAME)
		self.assertEqual(workflow.document_type, "GPS Installation")
		self.assertEqual(len(workflow.states), 7)
		self.assertGreaterEqual(len(workflow.transitions), 7)

	def test_submit_requires_checklist(self):
		doc = make_installation(self.fixture, checklist=[])
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		frappe.delete_doc("GPS Installation", doc.name, force=True)

	def test_submit_requires_result_on_every_row(self):
		doc = make_installation(self.fixture, checklist=[{"item": "Wiring", "result": ""}])
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		frappe.delete_doc("GPS Installation", doc.name, force=True)

	def test_submit_requires_platform_verification(self):
		doc = make_installation(self.fixture, platform_verified=0)
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		frappe.delete_doc("GPS Installation", doc.name, force=True)

	def test_submit_sets_installed(self):
		doc = make_installation(self.fixture, submit=True)
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(doc.status, "Installed")
		self.assertEqual(
			frappe.db.get_value("Serial No", self.fixture["serial"], "gps_asset_status"), "Installed"
		)
		doc.cancel()
		frappe.delete_doc("GPS Installation", doc.name, force=True)

	def test_qc_pass_updates_installation(self):
		installation = make_installation(self.fixture, submit=True)
		doc = make_inspection(installation, result="Pass", findings=None)
		doc.submit()
		self.assertEqual(
			frappe.db.get_value("GPS Installation", installation.name, "status"), "QC Passed"
		)

	def test_qc_fail_creates_non_conformance(self):
		installation = make_installation(self.fixture, submit=True)
		doc = make_inspection(
			installation, result="Fail", findings="Loose antenna, device offline on platform."
		)
		doc.submit()
		self.assertTrue(doc.non_conformance)
		self.assertEqual(
			frappe.db.get_value("Non Conformance", doc.non_conformance, "status"), "Open"
		)
		self.assertEqual(
			frappe.db.get_value("GPS Installation", installation.name, "status"), "QC Failed"
		)

	def test_qc_fail_requires_findings(self):
		installation = make_installation(self.fixture, submit=True)
		with self.assertRaises(frappe.ValidationError):
			make_inspection(installation, result="Fail", findings=None).submit()
