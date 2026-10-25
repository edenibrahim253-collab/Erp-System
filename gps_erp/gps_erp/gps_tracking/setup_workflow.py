import frappe

WORKFLOW_NAME = "GPS Installation Workflow"

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
	("Installed", "Send to QC", "Awaiting QC", ["GPS Fleet Manager", "System Manager"]),
	("Awaiting QC", "Pass QC", "QC Passed", ["GPS Fleet Manager", "System Manager"]),
	("Awaiting QC", "Fail QC", "QC Failed", ["GPS Fleet Manager", "System Manager"]),
	("QC Failed", "Rework Done", "Installed", ["GPS Technician", "GPS Fleet Manager", "System Manager"]),
	("QC Passed", "Close", "Closed", ["GPS Fleet Manager", "System Manager"]),
]


def sync_installation_workflow():
	if frappe.flags.in_test and not frappe.conf.get("developer_mode"):
		return

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
		frappe.delete_doc("Workflow", WORKFLOW_NAME, force=True, ignore_on_trash=True)

	workflow = frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": WORKFLOW_NAME,
			"document_type": "GPS Installation",
			"is_active": 1,
			"override_status": 0,
			"send_email_alert": 0,
			"states": [dict(state) for state in STATES],
			"transitions": [
				{"state": state, "action": action, "next_state": next_state, "allowed": role}
				for state, action, next_state, roles in TRANSITIONS
				for role in roles
			],
		}
	)
	workflow.insert(ignore_permissions=True)
