import datetime
import random

import frappe
from frappe.utils import getdate

FAR_FUTURE = datetime.date(9999, 12, 31)


def ranges_overlap(start_a, end_a, start_b, end_b):
	"""Two closed date ranges, an empty end meaning 'still open'."""
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
