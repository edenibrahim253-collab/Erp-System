import re

import frappe
from frappe import _

IMEI_RE = re.compile(r"^\d{15}$")


def validate(doc, method):
	if not doc.item_code:
		return
	if not frappe.db.get_value("Item", doc.item_code, "gps_is_device"):
		return

	imei = re.sub(r"[\s-]", "", str(doc.serial_no or doc.name or ""))
	if not IMEI_RE.match(imei):
		frappe.throw(
			_(
				"Serial No {0} is a GPS device item: the serial number must be a 15-digit IMEI."
			).format(frappe.bold(doc.item_code))
		)
