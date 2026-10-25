import frappe
from frappe.model.document import Document


class GPSBillingSettings(Document):
	pass


def get_settings() -> "GPSBillingSettings":
	return frappe.get_doc("GPS Billing Settings")
