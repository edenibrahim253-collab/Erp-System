import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class GPSSubscriptionAsset(Document):
	pass


def validate_subscription_assets(subscription, method=None):
	"""doc_events hook on Subscription: per-vehicle asset row rules.

	Child DocType controllers do not get their own validate() run, so the
	rules live here and fire whenever a Subscription is saved.
	"""
	for row in subscription.get("gps_subscription_assets") or []:
		if row.rate is not None and row.rate < 0:
			frappe.throw(
				_("Rate for vehicle {0} cannot be negative.").format(frappe.bold(row.vehicle))
			)
		if row.effective_from and row.effective_to and getdate(row.effective_to) < getdate(row.effective_from):
			frappe.throw(
				_("Effective To cannot be before Effective From for vehicle {0}.").format(
					frappe.bold(row.vehicle)
				)
			)
		if row.billing_status == "Terminated" and not row.effective_to:
			frappe.throw(_("Terminated vehicle {0} must have an Effective To date.").format(frappe.bold(row.vehicle)))
