import random
import unittest

import frappe
from frappe.utils import add_days, today

from gps_erp.gps_tracking.utils import make_test_imei

GPS_IMEI_ITEM = "_Test GPS Tracker"
GPS_CUSTOMER_GROUP = "_Test GPS Fleet"


def unique_digits(n):
	return str(random.randrange(10 ** (n - 1), 10**n))


def make_fixture_data():
	suffix = unique_digits(11)
	customer = f"_Test Assign Customer {suffix}"
	created = {"customer_group": False, "customer": False, "item": False}
	if not frappe.db.exists("Customer Group", GPS_CUSTOMER_GROUP):
		frappe.get_doc(
			{
				"doctype": "Customer Group",
				"customer_group_name": GPS_CUSTOMER_GROUP,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
		created["customer_group"] = True
	if not frappe.db.exists("Customer", {"customer_name": customer}):
		frappe.get_doc(
			{"doctype": "Customer", "customer_name": customer, "customer_group": GPS_CUSTOMER_GROUP}
		).insert(ignore_permissions=True)
		created["customer"] = True

	vehicle = frappe.get_doc(
		{"doctype": "GPS Vehicle", "license_plate": f"AS{suffix}", "customer": customer}
	)
	vehicle.insert(ignore_permissions=True)

	if not frappe.db.exists("Item", GPS_IMEI_ITEM):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": GPS_IMEI_ITEM,
				"item_name": GPS_IMEI_ITEM,
				"item_group": "Products",
				"stock_uom": frappe.db.get_value("UOM", None, "name") or "Nos",
				"is_stock_item": 1,
				"has_serial_no": 1,
				"gps_is_device": 1,
			}
		).insert(ignore_permissions=True)
		created["item"] = True

	serials = []
	for _i in range(2):
		serial = frappe.get_doc(
			{
				"doctype": "Serial No",
				"serial_no": make_test_imei(),
				"item_code": GPS_IMEI_ITEM,
				"status": "Active",
			}
		)
		serial.insert(ignore_permissions=True)
		serials.append(serial.name)

	sims = []
	for _i in range(2):
		sim = frappe.get_doc({"doctype": "GPS SIM Card", "iccid": "89100" + unique_digits(14)})
		sim.insert(ignore_permissions=True)
		sims.append(sim.name)

	return {
		"customer": customer,
		"vehicle": vehicle.name,
		"serial": serials[0],
		"serial2": serials[1],
		"sim": sims[0],
		"sim2": sims[1],
		"created": created,
	}


class TestGPSAssignments(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.fixture = make_fixture_data()
		cls.created_assignments = []

	@classmethod
	def tearDownClass(cls):
		for doctype, name in cls.created_assignments:
			if not frappe.db.exists(doctype, name):
				continue
			doc = frappe.get_doc(doctype, name)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc(doctype, name, force=True, ignore_missing=True)
		for name in (cls.fixture["serial"], cls.fixture["serial2"]):
			frappe.delete_doc("Serial No", name, force=True, ignore_missing=True)
		for name in (cls.fixture["sim"], cls.fixture["sim2"]):
			frappe.delete_doc("GPS SIM Card", name, force=True, ignore_missing=True)
		frappe.delete_doc("GPS Vehicle", cls.fixture["vehicle"], force=True, ignore_missing=True)
		created = cls.fixture["created"]
		if created["customer"]:
			frappe.delete_doc("Customer", cls.fixture["customer"], force=True, ignore_missing=True)
		if created["item"]:
			frappe.delete_doc("Item", GPS_IMEI_ITEM, force=True, ignore_missing=True)
		if created["customer_group"]:
			frappe.delete_doc("Customer Group", GPS_CUSTOMER_GROUP, force=True, ignore_missing=True)

	def make_assignment(self, doctype, **kwargs):
		fixture = self.fixture
		values = {"doctype": doctype, "assigned_on": "2026-01-01"}
		if doctype == "GPS Device Assignment":
			values.update({"serial_no": fixture["serial"], "vehicle": fixture["vehicle"]})
		else:
			values.update({"sim_card": fixture["sim"], "serial_no": fixture["serial"]})
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		self.created_assignments.append((doctype, doc.name))
		return doc

	def delete_assignment(self, doc):
		entry = (doc.doctype, doc.name)
		if entry in self.created_assignments:
			self.created_assignments.remove(entry)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc(doc.doctype, doc.name, force=True, ignore_missing=True)

	def test_device_overlap_rejected(self):
		first = self.make_assignment("GPS Device Assignment")
		try:
			with self.assertRaises(frappe.ValidationError):
				self.make_assignment("GPS Device Assignment", assigned_on="2026-02-01")
		finally:
			self.delete_assignment(first)

	def test_device_sequential_allowed(self):
		first = self.make_assignment("GPS Device Assignment", returned_on="2026-01-31")
		second = self.make_assignment("GPS Device Assignment", assigned_on="2026-02-01")
		self.assertEqual(first.status, "Closed")
		self.assertEqual(second.status, "Active")
		self.delete_assignment(first)
		self.delete_assignment(second)

	def test_device_boundary_day_overlap_rejected(self):
		# Closed range must end the day before the next one starts.
		first = self.make_assignment("GPS Device Assignment", returned_on="2026-01-31")
		try:
			with self.assertRaises(frappe.ValidationError):
				self.make_assignment("GPS Device Assignment", assigned_on="2026-01-31")
		finally:
			self.delete_assignment(first)

	def test_cancelled_assignment_does_not_block_reassignment(self):
		doc = self.make_assignment("GPS Device Assignment", returned_on="2026-01-31")
		doc.submit()
		doc.cancel()
		replacement = self.make_assignment(
			"GPS Device Assignment", assigned_on="2026-01-01", returned_on="2026-01-31"
		)
		self.assertEqual(replacement.status, "Closed")
		self.delete_assignment(replacement)

	def test_submit_sets_serial_status_and_cancel_reverts(self):
		doc = self.make_assignment("GPS Device Assignment", returned_on=None)
		doc.submit()
		self.assertEqual(
			frappe.db.get_value("Serial No", self.fixture["serial"], "gps_asset_status"), "Assigned"
		)
		doc.cancel()
		self.assertEqual(
			frappe.db.get_value("Serial No", self.fixture["serial"], "gps_asset_status"), "In Stock"
		)
		self.delete_assignment(doc)

	def test_submit_closed_assignment_does_not_assign_device(self):
		before = frappe.db.get_value("Serial No", self.fixture["serial2"], "gps_asset_status")
		doc = self.make_assignment(
			"GPS Device Assignment",
			serial_no=self.fixture["serial2"],
			returned_on="2026-01-31",
		)
		doc.submit()
		self.assertEqual(
			frappe.db.get_value("Serial No", self.fixture["serial2"], "gps_asset_status"), before
		)
		self.delete_assignment(doc)

	def test_cancel_keeps_non_assigned_device_status(self):
		doc = self.make_assignment("GPS Device Assignment")
		doc.submit()
		frappe.db.set_value("Serial No", self.fixture["serial"], "gps_asset_status", "Faulty")
		doc.cancel()
		self.assertEqual(
			frappe.db.get_value("Serial No", self.fixture["serial"], "gps_asset_status"), "Faulty"
		)
		self.delete_assignment(doc)

	def test_future_return_date_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_assignment("GPS Device Assignment", returned_on=add_days(today(), 5))

	def test_submitted_assignment_cannot_be_edited(self):
		doc = self.make_assignment("GPS Device Assignment")
		doc.submit()
		# re-fetch: the in-memory copy submitted via the Save transition keeps a
		# stale _original_modified, so save() on it would trip the timestamp check
		# before Frappe can report the docstatus violation.
		fresh = frappe.get_doc("GPS Device Assignment", doc.name)
		with self.assertRaises(frappe.ValidationError):
			fresh.returned_on = "2026-06-01"
			fresh.save()
		# the documented path is cancel + new assignment; overlap rules then apply
		doc.reload()
		doc.cancel()
		self.delete_assignment(doc)

	def test_sim_overlap_rejected(self):
		first = self.make_assignment("GPS SIM Assignment")
		try:
			with self.assertRaises(frappe.ValidationError):
				self.make_assignment("GPS SIM Assignment", assigned_on="2026-01-15")
		finally:
			self.delete_assignment(first)

	def test_sim_submit_activates_card(self):
		doc = self.make_assignment("GPS SIM Assignment")
		doc.submit()
		self.assertEqual(frappe.db.get_value("GPS SIM Card", self.fixture["sim"], "status"), "Activated")
		doc.cancel()
		self.assertEqual(frappe.db.get_value("GPS SIM Card", self.fixture["sim"], "status"), "Reserved")
		self.delete_assignment(doc)

	def test_submit_closed_assignment_does_not_activate_sim(self):
		before = frappe.db.get_value("GPS SIM Card", self.fixture["sim2"], "status")
		doc = self.make_assignment(
			"GPS SIM Assignment",
			sim_card=self.fixture["sim2"],
			released_on="2026-03-01",
		)
		doc.submit()
		self.assertEqual(frappe.db.get_value("GPS SIM Card", self.fixture["sim2"], "status"), before)
		self.delete_assignment(doc)

	def test_cancel_keeps_non_activated_sim_status(self):
		doc = self.make_assignment(
			"GPS SIM Assignment", sim_card=self.fixture["sim2"], serial_no=self.fixture["serial2"]
		)
		doc.submit()
		frappe.db.set_value("GPS SIM Card", self.fixture["sim2"], "status", "Blocked")
		doc.cancel()
		self.assertEqual(frappe.db.get_value("GPS SIM Card", self.fixture["sim2"], "status"), "Blocked")
		self.delete_assignment(doc)

	def test_future_release_date_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_assignment("GPS SIM Assignment", released_on=add_days(today(), 5))
