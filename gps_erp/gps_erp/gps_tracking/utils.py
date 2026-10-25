import datetime

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
