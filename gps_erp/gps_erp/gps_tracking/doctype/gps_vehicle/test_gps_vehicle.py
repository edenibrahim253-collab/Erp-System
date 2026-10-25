import time
import unittest

import frappe


def ensure_customer(customer_name="_Test GPS Fleet Customer"):
	existing = frappe.db.get_value("Customer", {"customer_name": customer_name}, "name")
	if existing:
		return existing
	group = "_Test GPS Fleet"
	if not frappe.db.exists("Customer Group", group):
		frappe.get_doc(
			{"doctype": "Customer Group", "customer_group_name": group, "is_group": 0}
		).insert(ignore_permissions=True)
	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": customer_name,
			"customer_group": group,
		}
	)
	customer.insert(ignore_permissions=True)
	return customer.name


def make_vehicle(plate, vin=None, customer_name="_Test GPS Fleet Customer"):
	doc = frappe.get_doc(
		{
			"doctype": "GPS Vehicle",
			"license_plate": plate,
			"vin_chassis": vin,
			"customer": ensure_customer(customer_name),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestGPSVehicle(unittest.TestCase):
	def setUp(self):
		self.suffix = str(int(time.time() * 1000))[-9:]

	def test_plate_normalization_and_naming(self):
		vehicle = make_vehicle(f"aa {self.suffix} bb")
		self.assertEqual(vehicle.name, f"AA{self.suffix}BB")
		frappe.delete_doc("GPS Vehicle", vehicle.name, force=True)

	def test_duplicate_vin_rejected(self):
		make_vehicle(f"V1{self.suffix}", vin=f"VIN{self.suffix}")
		try:
			with self.assertRaises(frappe.DuplicateEntryError):
				make_vehicle(f"V2{self.suffix}", vin=f"VIN{self.suffix}")
		finally:
			frappe.delete_doc("GPS Vehicle", f"V1{self.suffix}", force=True)

	def test_empty_vin_allowed_multiple(self):
		a = make_vehicle(f"E1{self.suffix}")
		b = make_vehicle(f"E2{self.suffix}")
		self.assertTrue(a.name and b.name)
		frappe.delete_doc("GPS Vehicle", a.name, force=True)
		frappe.delete_doc("GPS Vehicle", b.name, force=True)
