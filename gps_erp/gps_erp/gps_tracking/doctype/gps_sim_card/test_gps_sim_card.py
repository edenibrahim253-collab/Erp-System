import random
import unittest

import frappe

ICCID_BASE = "89100"


def make_sim(iccid=None, msisdn=None, **kwargs):
	if iccid is None:
		iccid = f"{ICCID_BASE}{random.randrange(10**13, 10**14)}"
	doc = frappe.get_doc(
		{
			"doctype": "GPS SIM Card",
			"iccid": iccid,
			"msisdn": msisdn,
			**kwargs,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestGPSSIMCard(unittest.TestCase):
	def tearDown(self):
		for name in frappe.get_all("GPS SIM Card", pluck="name"):
			if name.startswith(ICCID_BASE):
				frappe.delete_doc("GPS SIM Card", name, force=True, ignore_missing=True)

	def test_leading_zeros_and_separators_normalized(self):
		sim = make_sim(iccid=" 89 100-0123456789012 ")
		self.assertEqual(sim.name, "891000123456789012")
		self.assertTrue(sim.name.startswith("89"))

	def test_duplicate_iccid_rejected(self):
		sim = make_sim()
		with self.assertRaises(frappe.DuplicateEntryError):
			make_sim(iccid=sim.name)

	def test_duplicate_msisdn_rejected(self):
		make_sim(msisdn="+251 91 123 4567")
		with self.assertRaises(frappe.DuplicateEntryError):
			make_sim(msisdn="+251911234567")

	def test_invalid_iccid_format_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_sim(iccid="12345")

	def test_expiry_before_activation_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_sim(activation_date="2026-06-01", expiry_date="2026-01-01")
