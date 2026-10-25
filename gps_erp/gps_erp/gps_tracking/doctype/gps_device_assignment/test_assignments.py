import random
import unittest

import frappe

GPS_IMEI_ITEM = "_Test GPS Tracker"


def unique_digits(n):
	return str(random.randrange(10 ** (n - 1), 10**n))


def make_fixture_data():
	suffix = unique_digits(11)
	customer = f"_Test Assign Customer {suffix}"
	if not frappe.db.exists("Customer", {"customer_name": customer}):
		group = "_Test GPS Fleet"
		if not frappe.db.exists("Customer Group", group):
			frappe.get_doc({"doctype": "Customer Group", "customer_group_name": group, "is_group": 0}).insert(
				ignore_permissions=True
			)
		frappe.get_doc({"doctype": "Customer", "customer_name": customer, "customer_group": group}).insert(
			ignore_permissions=True
		)

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

	serial = frappe.get_doc(
		{
			"doctype": "Serial No",
			"serial_no": unique_digits(15),
			"item_code": GPS_IMEI_ITEM,
			"status": "Active",
		}
	)
	serial.insert(ignore_permissions=True)

	sim = frappe.get_doc({"doctype": "GPS SIM Card", "iccid": "89100" + unique_digits(14)})
	sim.insert(ignore_permissions=True)

	return {"customer": customer, "vehicle": vehicle.name, "serial": serial.name, "sim": sim.name}


def make_assignment(fixture, doctype, **kwargs):
	values = {
		"doctype": doctype,
		"assigned_on": "2026-01-01",
	}
	if doctype == "GPS Device Assignment":
		values.update({"serial_no": fixture["serial"], "vehicle": fixture["vehicle"]})
	else:
		values.update({"sim_card": fixture["sim"], "serial_no": fixture["serial"]})
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.insert(ignore_permissions=True)
	return doc


class TestGPSAssignments(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.fixture = make_fixture_data()

	@classmethod
	def tearDownClass(cls):
		for dt in ("GPS Device Assignment", "GPS SIM Assignment"):
			for name in frappe.get_all(dt, pluck="name"):
				frappe.delete_doc(dt, name, force=True, ignore_missing=True)
		frappe.delete_doc("Serial No", cls.fixture["serial"], force=True, ignore_missing=True)
		frappe.delete_doc("GPS SIM Card", cls.fixture["sim"], force=True, ignore_missing=True)
		frappe.delete_doc("GPS Vehicle", cls.fixture["vehicle"], force=True, ignore_missing=True)

	def test_device_overlap_rejected(self):
		first = make_assignment(self.fixture, "GPS Device Assignment")
		try:
			with self.assertRaises(frappe.ValidationError):
				make_assignment(self.fixture, "GPS Device Assignment", assigned_on="2026-02-01")
		finally:
			frappe.delete_doc("GPS Device Assignment", first.name, force=True)

	def test_device_sequential_allowed(self):
		first = make_assignment(
			self.fixture, "GPS Device Assignment", returned_on="2026-01-31"
		)
		second = make_assignment(self.fixture, "GPS Device Assignment", assigned_on="2026-02-01")
		self.assertEqual(first.status, "Closed")
		self.assertEqual(second.status, "Active")
		frappe.delete_doc("GPS Device Assignment", first.name, force=True)
		frappe.delete_doc("GPS Device Assignment", second.name, force=True)

	def test_submit_sets_serial_status_and_cancel_reverts(self):
		doc = make_assignment(self.fixture, "GPS Device Assignment", returned_on=None)
		doc.submit()
		self.assertEqual(
			frappe.db.get_value("Serial No", self.fixture["serial"], "gps_asset_status"), "Assigned"
		)
		doc.cancel()
		self.assertEqual(
			frappe.db.get_value("Serial No", self.fixture["serial"], "gps_asset_status"), "In Stock"
		)
		frappe.delete_doc("GPS Device Assignment", doc.name, force=True)

	def test_sim_overlap_rejected(self):
		first = make_assignment(self.fixture, "GPS SIM Assignment")
		try:
			with self.assertRaises(frappe.ValidationError):
				make_assignment(self.fixture, "GPS SIM Assignment", assigned_on="2026-01-15")
		finally:
			frappe.delete_doc("GPS SIM Assignment", first.name, force=True)

	def test_sim_submit_activates_card(self):
		doc = make_assignment(self.fixture, "GPS SIM Assignment", returned_on="2026-03-01")
		doc.submit()
		self.assertEqual(frappe.db.get_value("GPS SIM Card", self.fixture["sim"], "status"), "Activated")
		doc.cancel()
		frappe.delete_doc("GPS SIM Assignment", doc.name, force=True)
