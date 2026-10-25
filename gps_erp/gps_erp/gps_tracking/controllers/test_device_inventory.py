import unittest

import frappe

GPS_IMEI = "356971072936989"


def make_gps_item():
	item_code = "_Test GPS Tracker"
	if not frappe.db.exists("Item", item_code):
		uom = frappe.db.get_value("UOM", None, "name") or "Nos"
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_code,
				"item_group": "Products",
				"stock_uom": uom,
				"is_stock_item": 1,
				"has_serial_no": 1,
				"gps_is_device": 1,
				"gps_device_type": "Tracker",
			}
		).insert(ignore_permissions=True)
	return item_code


def make_serial(serial_no, item_code=None):
	doc = frappe.get_doc(
		{
			"doctype": "Serial No",
			"serial_no": serial_no,
			"item_code": item_code or make_gps_item(),
			"status": "Active",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestGPSDeviceInventory(unittest.TestCase):
	def tearDown(self):
		frappe.delete_doc("Serial No", GPS_IMEI, force=True, ignore_missing=True)
		frappe.delete_doc("Serial No", "12345", force=True, ignore_missing=True)

	def test_custom_fields_synced(self):
		self.assertTrue(frappe.db.exists("Custom Field", "Serial No-gps_asset_status"))
		self.assertTrue(frappe.db.exists("Custom Field", "Item-gps_is_device"))

	def test_valid_imei_accepted(self):
		serial = make_serial(GPS_IMEI)
		self.assertEqual(serial.name, GPS_IMEI)

	def test_non_imei_serial_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_serial("12345")

	def test_duplicate_imei_rejected(self):
		make_serial(GPS_IMEI)
		with self.assertRaises(frappe.DuplicateEntryError):
			make_serial(GPS_IMEI)
