import frappe
from frappe import _

WORKFLOW_NAME = "GPS Installation Workflow"
DOCUMENT_TYPE = "GPS Installation"
# The workflow drives the DocType's own `status` Select field, so the Python
# controllers (GPSInstallation.on_submit, GPS Service Inspection) and the
# workflow buttons read and write the same field — one status, one design.
STATE_FIELD = "status"

STATES = [
	{"state": "Pending", "doc_status": "0", "allow_edit": "GPS Technician"},
	{"state": "In Progress", "doc_status": "0", "allow_edit": "GPS Technician"},
	{"state": "Installed", "doc_status": "1", "allow_edit": "GPS Technician"},
	{"state": "Awaiting QC", "doc_status": "1", "allow_edit": "GPS Fleet Manager"},
	{"state": "QC Passed", "doc_status": "1", "allow_edit": "GPS Fleet Manager"},
	{"state": "QC Failed", "doc_status": "1", "allow_edit": "GPS Technician"},
	{"state": "Closed", "doc_status": "1", "allow_edit": "GPS Fleet Manager"},
]

TRANSITIONS = [
	("Pending", "Start Work", "In Progress", ["GPS Technician", "GPS Fleet Manager", "System Manager"]),
	("In Progress", "Mark Installed", "Installed", ["GPS Technician", "GPS Fleet Manager", "System Manager"]),
	# direct Submit button path: Save (draft) > Submit jumps straight to Installed
	("Pending", "Mark Installed", "Installed", ["GPS Technician", "GPS Fleet Manager", "System Manager"]),
	("Installed", "Send to QC", "Awaiting QC", ["GPS Fleet Manager", "System Manager"]),
	("Awaiting QC", "Pass QC", "QC Passed", ["GPS Fleet Manager", "System Manager"]),
	("Awaiting QC", "Fail QC", "QC Failed", ["GPS Fleet Manager", "System Manager"]),
	("QC Failed", "Rework Done", "Installed", ["GPS Technician", "GPS Fleet Manager", "System Manager"]),
	("QC Passed", "Close", "Closed", ["GPS Fleet Manager", "System Manager"]),
]


def _target_signature():
	return (
		STATE_FIELD,
		sorted((s["state"], s["doc_status"], s["allow_edit"]) for s in STATES),
		sorted(
			(t["state"], t["action"], t["next_state"], t["allowed"])
			for t in _target_transitions()
		),
	)


def _current_signature(workflow):
	return (
		workflow.workflow_state_field,
		sorted((s.state, s.doc_status, s.allow_edit) for s in workflow.states),
		sorted((t.state, t.action, t.next_state, t.allowed) for t in workflow.transitions),
	)


def _target_transitions():
	return [
		{"state": state, "action": action, "next_state": next_state, "allowed": role}
		for state, action, next_state, roles in TRANSITIONS
		for role in roles
	]


def sync_installation_workflow():
	"""Ensure the GPS Installation workflow matches the code definition.

	The workflow states/transitions are managed entirely by this app: any
	structural drift is reconciled in place (the Workflow document is never
	deleted and recreated, so history, naming and admin choices survive).
	`is_active` is only set on first creation; afterwards administrators may
	disable the workflow and migrations will not re-enable it.
	"""
	for state in STATES:
		if not frappe.db.exists("Workflow State", state["state"]):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": state["state"]}
			).insert(ignore_permissions=True)

	for _s, action, _n, _roles in TRANSITIONS:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)

	if frappe.db.exists("Workflow", WORKFLOW_NAME):
		workflow = frappe.get_doc("Workflow", WORKFLOW_NAME)
		if workflow.document_type == DOCUMENT_TYPE and _current_signature(workflow) == _target_signature():
			return
		workflow.workflow_state_field = STATE_FIELD
		workflow.set("states", [])
		workflow.set("transitions", [])
		for state in STATES:
			workflow.append("states", dict(state))
		for transition in _target_transitions():
			workflow.append("transitions", transition)
		workflow.save(ignore_permissions=True)
		return

	workflow = frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": WORKFLOW_NAME,
			"document_type": DOCUMENT_TYPE,
			"workflow_state_field": STATE_FIELD,
			"is_active": 1,
			"override_status": 0,
			"send_email_alert": 0,
			"states": [dict(state) for state in STATES],
			"transitions": _target_transitions(),
		}
	)
	workflow.insert(ignore_permissions=True)


# --- the only sanctioned way for controllers to move an installation's status ---

# Reverse moves allowed solely when a QC document is cancelled (data
# correction, gated by the cancel permission on GPS Service Inspection).
CORRECTION_MOVES = {
	("QC Passed", "Installed"),
	("QC Passed", "QC Failed"),
	("QC Failed", "Installed"),
	("QC Failed", "QC Passed"),
	("Awaiting QC", "Installed"),
}

FORWARD_MOVES = {(state, next_state) for state, _action, next_state, _roles in TRANSITIONS}


def set_installation_status(name, target, correction=False):
	"""Move a GPS Installation to `target` only along the workflow graph.

	Every scripted status write goes through here, so a controller cannot
	jump an installation to a state no defined transition leads to. Pass
	`correction=True` only from QC cancellation, which rolls the status back
	to what the remaining submitted inspections say.
	"""
	current = frappe.db.get_value("GPS Installation", name, "status")
	if current == target:
		return

	allowed = FORWARD_MOVES | (CORRECTION_MOVES if correction else set())
	if (current, target) not in allowed:
		frappe.throw(
			_("Status move {0} \u2192 {1} is not a valid workflow transition for installation {2}.").format(
				current, target, name
			)
		)
	frappe.db.set_value("GPS Installation", name, "status", target, update_modified=False)
