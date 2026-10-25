import datetime
import random

import frappe
from frappe.utils import getdate

FAR_FUTURE = datetime.date(9999, 12, 31)


def ranges_overlap(start_a, end_a, start_b, end_b):
	"""Two closed date ranges, an empty end meaning 'still open'.

	Touching boundary dates overlap: a range ending 2026-01-31 conflicts with
	one starting 2026-01-31. Sequential assignments must start the next day.
	"""
	a_start = getdate(start_a)
	a_end = getdate(end_a) or FAR_FUTURE
	b_start = getdate(start_b)
	b_end = getdate(end_b) or FAR_FUTURE
	return a_start <= b_end and b_start <= a_end


def make_test_imei(first_14=None):
	"""Random 15-digit IMEI with a valid Luhn check digit, for test fixtures."""
	if first_14 is None:
		first_14 = str(random.randrange(10**13, 10**14))
	total = 0
	for index, char in enumerate(reversed(first_14)):
		digit = int(char)
		if index % 2 == 0:
			digit *= 2
			if digit > 9:
				digit -= 9
		total += digit
	return first_14 + str((10 - total % 10) % 10)


def revert_installed_device(serial_no):
	"""Undo the "Installed" device status an installation submission set.

	gps_asset_status has exactly two writers: the assignment doctypes move the
	device between In Stock and Assigned, the installation moves it to
	Installed. This third writer re-derives the device from the assignment
	rules and never overwrites a status the installation did not cause
	(Installed is the only value it accepts), so cancelling an installation
	cannot corrupt Faulty/Blocked/Assigned states set by other means.
	"""
	if frappe.db.get_value("Serial No", serial_no, "gps_asset_status") != "Installed":
		return
	if frappe.db.exists(
		"GPS Device Assignment", {"serial_no": serial_no, "status": "Active", "docstatus": 1}
	):
		status = "Assigned"
	else:
		status = "In Stock"
	frappe.db.set_value("Serial No", serial_no, "gps_asset_status", status, update_modified=False)
