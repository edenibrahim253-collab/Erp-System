import unittest

import frappe
import frappe.defaults

from gps_erp.gps_tracking.doctype.gps_device_assignment.test_assignments import (
	GPS_IMEI_ITEM,
	make_fixture_data,
)


def test_company():
	return frappe.defaults.get_user_default("Company") or frappe.db.get_value("Company", None, "name")


class TestBillingDataModel(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.fixture = make_fixture_data()
		cls.created = cls.fixture["created"]
		cls.created_docs = []
		cls.plan_existed = bool(frappe.db.exists("Subscription Plan", "GPS Fleet Test Plan"))

	@classmethod
	def tearDownClass(cls):
		for doctype, name in reversed(cls.created_docs):
			if not frappe.db.exists(doctype, name):
				continue
			doc = frappe.get_doc(doctype, name)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc(doctype, name, force=True, ignore_missing=True)
		if not cls.plan_existed:
			frappe.delete_doc("Subscription Plan", "GPS Fleet Test Plan", force=True, ignore_missing=True)
		for name in (cls.fixture["serial"], cls.fixture["serial2"]):
			frappe.delete_doc("Serial No", name, force=True, ignore_missing=True)
		for name in (cls.fixture["sim"], cls.fixture["sim2"]):
			frappe.delete_doc("GPS SIM Card", name, force=True, ignore_missing=True)
		frappe.delete_doc("GPS Vehicle", cls.fixture["vehicle"], force=True, ignore_missing=True)
		created = cls.created
		if created.get("customer"):
			frappe.delete_doc("Customer", cls.fixture["customer"], force=True, ignore_missing=True)
		if created.get("item"):
			frappe.delete_doc("Item", GPS_IMEI_ITEM, force=True, ignore_missing=True)
		if created.get("customer_group"):
			frappe.delete_doc("Customer Group", "_Test GPS Fleet", force=True, ignore_missing=True)

	def track(self, doctype, name):
		self.created_docs.append((doctype, name))

	def ensure_plan(self):
		if frappe.db.exists("Subscription Plan", "GPS Fleet Test Plan"):
			return frappe.get_cached_doc("Subscription Plan", "GPS Fleet Test Plan")
		plan = frappe.get_doc(
			{
				"doctype": "Subscription Plan",
				"plan_name": "GPS Fleet Test Plan",
				"item": GPS_IMEI_ITEM,
				"price_determination": "Fixed Rate",
				"cost": 100,
				"currency": frappe.db.get_value("Company", test_company(), "default_currency"),
				"billing_interval": "Month",
				"billing_interval_count": 1,
			}
		)
		plan.insert(ignore_permissions=True)
		return plan

	def make_subscription(self, assets=None):
		plan = self.ensure_plan()
		sub = frappe.get_doc(
			{
				"doctype": "Subscription",
				"customer": self.fixture["customer"],
				"party_type": "Customer",
				"party": self.fixture["customer"],
				"company": test_company(),
				"start_date": "2026-01-01",
				"status": "Active",
				"plans": [{"plan": plan.name, "qty": 1}],
				"gps_subscription_assets": [dict(row) for row in (assets or [])],
			}
		)
		sub.insert(ignore_permissions=True)
		self.track("Subscription", sub.name)
		return sub

	def asset_row(self, **kwargs):
		row = {
			"vehicle": self.fixture["vehicle"],
			"item": GPS_IMEI_ITEM,
			"rate": 50,
			"billing_status": "Active",
			"effective_from": "2026-01-01",
		}
		row.update(kwargs)
		return row

	def test_doctypes_exist(self):
		self.assertTrue(frappe.db.exists("DocType", "GPS Subscription Asset"))
		self.assertTrue(frappe.db.exists("DocType", "GPS Billing Settings"))

	def test_custom_field_on_subscription(self):
		meta = frappe.get_meta("Subscription")
		field = meta.get_field("gps_subscription_assets")
		self.assertIsNotNone(field)
		self.assertEqual(field.fieldtype, "Table")
		self.assertEqual(field.options, "GPS Subscription Asset")

	def test_settings_single_defaults_and_save(self):
		settings = frappe.get_doc("GPS Billing Settings")
		self.assertEqual(settings.suspension_grace_days, 5)
		settings.enable_auto_billing = 1
		settings.finance_approval_threshold = 5000
		settings.save()
		reloaded = frappe.get_doc("GPS Billing Settings")
		self.assertEqual(reloaded.enable_auto_billing, 1)
		# restore the safe default so the nightly job is not left enabled
		settings = frappe.get_doc("GPS Billing Settings")
		settings.enable_auto_billing = 0
		settings.finance_approval_threshold = 0
		settings.save()

	def test_asset_rows_round_trip_on_subscription(self):
		sub = self.make_subscription(assets=[self.asset_row(), self.asset_row(rate=75)])
		reloaded = frappe.get_doc("Subscription", sub.name)
		self.assertEqual(len(reloaded.gps_subscription_assets), 2)
		self.assertEqual(reloaded.gps_subscription_assets[1].rate, 75)

	def test_negative_rate_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_subscription(assets=[self.asset_row(rate=-1)])

	def test_effective_window_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_subscription(
				assets=[self.asset_row(effective_from="2026-02-01", effective_to="2026-01-01")]
			)

	def test_terminated_row_keeps_history(self):
		sub = self.make_subscription(
			assets=[self.asset_row(billing_status="Terminated", effective_to="2026-03-31")]
		)
		reloaded = frappe.get_doc("Subscription", sub.name)
		row = reloaded.gps_subscription_assets[0]
		self.assertEqual(row.billing_status, "Terminated")
		self.assertEqual(str(row.effective_to), "2026-03-31")

	def test_terminated_row_requires_effective_to(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_subscription(assets=[self.asset_row(billing_status="Terminated")])
