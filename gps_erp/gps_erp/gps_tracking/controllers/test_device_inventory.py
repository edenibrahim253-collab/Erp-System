import unittest

import frappe

from gps_erp.gps_tracking.controllers.serial_no import is_valid_imei

GPS_ITEM = "_Test GPS Tracker"


def luhn_check_digit(first_14):
	total = 0
	for index, char in enumerate(reversed(first_14)):
		digit = int(char)
		if index % 2 == 0:
			digit *= 2
			if digit > 9:
				digit -= 9
		total += digit
	return str((10 - total % 10) % 10)


def valid_imei(first_14="35697107293698"):
	return first_14 + luhn_check_digit(first_14)


GPS_IMEI = valid_imei()


class TestGPSDeviceInventory(unittest.TestCase):
	def setUp(self):
		self.created_serials = []
		if not frappe.db.exists("Item", GPS_ITEM):
			uom = frappe.db.get_value("UOM", None, "name") or "Nos"
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": GPS_ITEM,
					"item_name": GPS_ITEM,
					"item_group": "Products",
					"stock_uom": uom,
					"is_stock_item": 1,
					"has_serial_no": 1,
					"gps_is_device": 1,
					"gps_device_type": "Tracker",
				}
			).insert(ignore_permissions=True)

	def tearDown(self):
		for name in self.created_serials:
			if frappe.db.exists("Serial No", name):
				frappe.delete_doc("Serial No", name, force=True, ignore_missing=True)

	def make_serial(self, serial_no):
		doc = frappe.get_doc(
			{
				"doctype": "Serial No",
				"serial_no": serial_no,
				"item_code": GPS_ITEM,
				"status": "Active",
			}
		)
		doc.insert(ignore_permissions=True)
		self.created_serials.append(doc.name)
		return doc

	def test_fixture_imei_passes_luhn(self):
		self.assertTrue(is_valid_imei(GPS_IMEI))

	def test_custom_fields_synced(self):
		self.assertTrue(frappe.db.exists("Custom Field", "Serial No-gps_asset_status"))
		self.assertTrue(frappe.db.exists("Custom Field", "Item-gps_is_device"))

	def test_valid_imei_accepted(self):
		serial = self.make_serial(GPS_IMEI)
		self.assertEqual(serial.name, GPS_IMEI)

	def test_non_imei_serial_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_serial("12345")

	def test_bad_check_digit_rejected(self):
		broken = GPS_IMEI[:-1] + str((int(GPS_IMEI[-1]) + 1) % 10)
		with self.assertRaises(frappe.ValidationError):
			self.make_serial(broken)

	def test_separators_normalized_before_save(self):
		serial = self.make_serial(f"{GPS_IMEI[:2]}-{GPS_IMEI[2:8]}-{GPS_IMEI[8:14]}-{GPS_IMEI[14]}")
		self.assertEqual(serial.name, GPS_IMEI)
		self.assertEqual(serial.serial_no, GPS_IMEI)
		self.assertEqual(frappe.db.get_value("Serial No", GPS_IMEI, "serial_no"), GPS_IMEI)

	def test_duplicate_imei_rejected(self):
		self.make_serial(GPS_IMEI)
		with self.assertRaises(frappe.DuplicateEntryError):
			self.make_serial(GPS_IMEI)
