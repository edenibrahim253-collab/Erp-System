import re

import frappe
from frappe import _

IMEI_RE = re.compile(r"^\d{15}$")


def is_valid_imei(imei):
	"""Luhn check over all 15 digits (IMEI uses the standard mod-10 scheme)."""
	total = 0
	for index, char in enumerate(reversed(imei)):
		digit = int(char)
		if index % 2 == 1:
			digit *= 2
			if digit > 9:
				digit -= 9
		total += digit
	return total % 10 == 0


def validate(doc, method):
	if not doc.item_code:
		return
	if not frappe.db.get_value("Item", doc.item_code, "gps_is_device"):
		return

	raw = str(doc.serial_no or doc.name or "")
	imei = re.sub(r"[\s-]", "", raw)
	if not IMEI_RE.match(imei):
		frappe.throw(
			_(
				"Serial No {0} is a GPS device item: the serial number must be a 15-digit IMEI."
			).format(frappe.bold(doc.item_code))
		)
	if not is_valid_imei(imei):
		frappe.throw(
			_(
				"Serial No {0} is not a valid IMEI: the check digit (Luhn) does not match."
			).format(frappe.bold(imei))
		)

	if imei != raw:
		doc.serial_no = imei
		if doc.is_new():
			doc.name = imei
