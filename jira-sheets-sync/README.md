# JIRA → Google Sheets Sync

A Google Apps Script tool that automatically syncs JIRA Data Center issue statuses and dates into a Google Sheet. Each team runs their own copy — the script lives inside the sheet and requires no server or local installation.

---

## What It Does

- Reads issues from JIRA via configurable JQL (your team's scope)
- Classifies each issue's status using your board's swimlane JQL rules
- Compares computed values against what's currently in the sheet
- Presents a **pre-flight approval dialog** before writing any changes
- Sends an email digest of what changed, what's new in JIRA, and what rows are missing
- Runs on demand via a sheet menu, or automatically on a daily schedule

**Columns it manages:**

| Column | Field | Source |
|---|---|---|
| Configurable (default: JIRA Key column) | JIRA Key | Read-only — used for row matching |
| Configurable (default: Status) | Derived Status | Computed from your swimlane JQL rules |
| Configurable (default: Target Start Date) | Start Date | JIRA custom field `customfield_19601` — only written if JIRA has a value |
| Configurable (default: Target End Date) | Target End Date | JIRA custom field `customfield_19602` — only written if JIRA has a value |
| Configurable (default: Actual End Date) | Actual End Date | JIRA `resolutiondate` — written when issue is resolved |

All other columns are never touched.

---

## Prerequisites

- **JIRA Data Center** with REST API access (publicly reachable, not VPN-only)
- **Adaptavist ScriptRunner** plugin on your JIRA instance (required if your swimlane JQL uses `issueFunction in parentsOf(...)`)
- **Google Workspace** org account (the script uses Gmail and Sheets APIs)
- JIRA credentials: either a username + password, or a Personal Access Token (PAT) from your JIRA profile

---

## Installation

### 1. Create the Script Project

1. Open your Google Sheet
2. Go to **Extensions → Apps Script**
3. In the Script Editor, delete the default `Code.gs` file
4. Create the following files by clicking **+** → **Script** or **HTML** for each:

| File | Type |
|---|---|
| `main.gs` | Script |
| `jira.gs` | Script |
| `statusRules.gs` | Script |
| `sheets.gs` | Script |
| `state.gs` | Script |
| `email.gs` | Script |
| `ui.gs` | Script |
| `settings.html` | HTML |
| `approval.html` | HTML |

5. Paste the contents of each corresponding file from this package into the matching file in the Script Editor
6. Click **Save** (Ctrl+S)

### 2. Authorize the Script

1. In the Script Editor, select `onOpen` from the function dropdown when main.gs is open and click **▶ Run**
2. Google will prompt you to review and grant permissions — click through and authorize
3. Close the Script Editor tab

### 3. Reload the Sheet

Refresh the Google Sheet (Ctrl-F5). A **JIRA Sync** menu should appear in the menu bar.

---

## First-Time Configuration

Click **JIRA Sync → Settings** to open the configuration dialog. It has two tabs:

### Global Tab

These settings apply to all sheet tabs that use this script.

**JIRA Connection**
- **JIRA Base URL**: Your JIRA DC instance URL (e.g., `https://jira.example.com`)
- **Auth Type**: Select *Basic Auth* for username + password, or *Personal Access Token* if your JIRA admin issued you a PAT
- **Username / Token**: Your JIRA credentials (stored in User Properties — not visible to other sheet editors)

**Column Headers**
Enter the exact text of your row 1 headers for each managed column. The script finds columns by name, so inserting columns never breaks things.

- Default values: `JIRA`, `Status`, `Target Start Date`, `Target End Date`, `Actual End Date`
- Change these to match whatever your sheet's row 1 actually says

**Default Status Mappings**
The JQL rules that classify each issue's status. Listed in **progression order** (earliest stage first). The script evaluates from **most advanced to least advanced** — so a story qualifying for both Designing and Coding gets Coding.

- Enter the JIRA JQL for each status label
- Use **▶ Test** next to each row to validate against live JIRA data before saving
- Rows with blank JQL are skipped during classification
- BLOCKED and HOLD are not listed here — they are [manual designations](#blocked-and-hold)

### Tab Tab (Per-Tab Settings)

Labelled with the name of the sheet tab you're currently on. Each tab configures independently.

- **Main JQL**: The scope filter defining which JIRA issues this tab tracks (e.g., `project = XLIS AND issuetype = Story AND team = "My Team"`)
- **Daily Notification Emails**: Comma-separated addresses to email on scheduled runs
- **Include in daily schedule**: When checked, this tab is included in the automated daily sync
- **Custom status mapping overrides**: Optionally override the global default JQL rules for just this tab

Click **Save & Close** to save all settings.

---

## Running a Sync

### Manual (Run Now)

Click **JIRA Sync → Run Now** from the sheet menu. The script will:

1. Fetch all issues in scope from JIRA (Pass 1 — scope detection)
2. For each row in the sheet, fetch details and classify status (Pass 2 — per-issue)
3. Open the **Review Changes** dialog showing all proposed changes before anything is written

**Review Changes dialog:**
- Each issue with a proposed change shows a pre-checked checkbox with before → after values
- Uncheck any changes you don't want applied
- Click **Apply Selected** to write the approved changes and send the email digest
- Click **Cancel** to exit without writing anything and without sending email
- Informational sections (new JIRA issues not in sheet, rows not found in JIRA, unclassified issues) are shown for awareness but have no checkboxes

### Scheduled (Daily)

Click **JIRA Sync → Add This Tab to Daily Schedule** to register the current tab for daily automatic sync. Scheduled runs:

- Apply all changes directly without an approval dialog
- Email the notification addresses configured for the tab
- Run at 8 AM in the script's time zone

To schedule a different time or remove a tab from the schedule, go to the Script Editor → **Triggers** (clock icon).

> **Important — who the trigger runs as:**
> GAS time-based triggers run using the **Google account of the person who created the trigger**. This means:
>
> - The trigger owner's Google account permissions govern what the script can write in the sheet. If the sheet has tab-level or range-level edit restrictions, the trigger runs within the same restrictions as that person.
> - The trigger owner's **JIRA credentials** (set via Settings) are used for JIRA authentication on scheduled runs.
> - The trigger owner must open **Settings** and save their JIRA credentials **before** setting up the trigger. If credentials are missing for the trigger owner, the scheduled run exits silently and logs a message to the Script Editor's Execution Log.
>
> **Best practice:** Designate one person per team as the trigger owner. That person opens Settings, saves their credentials, then clicks "Add This Tab to Daily Schedule." Other team members can still run manual syncs with their own credentials.

---

## Status Classification Rules

Status rules are evaluated from **most advanced to least advanced** (bottom of the list to top). The first rule that matches wins.

This means:
- A story with both a completed Design subtask and an active Coding subtask → classified as **Coding**
- Rules don't need to be mutually exclusive — the most advanced applicable status always wins

**Rule format** (using ScriptRunner's `parentsOf`):
```
status = "In Progress" AND issueFunction in parentsOf("issuetype = Coding AND status not in (Open, Complete, Rejected, 'Peer Review', 'PR Complete')")
```

The script automatically rewrites `parentsOf` queries as targeted `parent = KEY AND (...)` lookups — this is far faster than a project-wide scan.

**Rules with no JQL entered are skipped.** Any issue that matches no rule appears in the email digest as "Unclassified — check your status mappings."

---

## BLOCKED and HOLD

BLOCKED and HOLD are **manually set by humans** — they are not automated statuses and do not appear in the status mappings JQL list.

**Behavior:**
- If a status cell currently contains `BLOCKED` or `HOLD`, the script will not overwrite it on any sync run
- The only exception: if the script classifies the issue as `Complete` (meaning the story is genuinely done), the cell is updated to `Complete`
- To un-block/un-hold a story, simply clear or change the status cell manually — the next sync will resume normal classification

---

## Email Digest

After each sync, an email is sent containing:

| Section | Meaning |
|---|---|
| **Status Changes** | Issues where status or dates were updated, with before → after values |
| **New Stories in JIRA** | Issues matching your scope JQL that have no row in the sheet — add them manually |
| **Rows Not Found in JIRA** | Sheet rows whose JIRA key wasn't returned by your scope JQL — verify and remove if rejected |
| **Unclassified Issues** | Issues that matched no status mapping JQL — check your mappings |

For **manual runs**, the email goes to whoever clicked Run Now.  
For **scheduled runs**, the email goes to the notification addresses in the tab's settings.

---

## Distributing to Other Teams

Each team makes their own copy of this sheet. When a Google Sheet is copied, the Apps Script code is included but Script Properties (settings and credentials) are not — each team configures their own.

### To pre-load your JQL into new copies:

1. In the Script Editor on your fully-configured sheet, select `generateDefaultMappingsCode` from the function dropdown and click **Run**
2. Open the **Execution Log** — it shows the complete `DEFAULT_STATUS_MAPPINGS` JavaScript constant with all your JQL values
3. Copy that block and replace the `DEFAULT_STATUS_MAPPINGS` constant at the top of `main.gs`
4. Save — now every future copy starts with your JQL pre-populated

### What each team needs to configure after making a copy:

1. Open Settings → **Global tab**: enter JIRA credentials
2. Open Settings → **Tab tab**: enter their team-specific Main JQL and notification emails
3. Run `onOpen` from the Script Editor to authorize (first time only), then reload the sheet

All other settings (column headers, status mappings) are inherited from the pre-loaded defaults.

---

## Troubleshooting

**"Column header not found in row 1"**  
The header name in Settings doesn't exactly match row 1. Open Settings → Global → Column Headers and check for typos or extra spaces.

**403 Forbidden**  
- If using a PAT, make sure Auth Type is set to *Personal Access Token* in Settings
- If using Basic Auth, confirm your JIRA DC instance allows basic auth (some orgs disable it for SSO)
- Verify your account has Browse permission for the project in your Main JQL

**"JQL error in status mapping"**  
The error message includes the status label whose JQL failed. Open Settings, find that row, click ▶ Test to see the exact JIRA error message.

**Changes appear on every run (date fields)**  
If date columns are formatted as dates in Sheets, `getValues()` returns JavaScript Date objects. The script normalizes these automatically. If you still see repeated date changes, check that the date format in the cell matches `yyyy-MM-dd`.

**Sync takes longer than expected**  
Each sheet row makes approximately 1 JIRA API call per status mapping until a match is found (evaluated from most advanced to least). With 13 status mappings and 50 rows, worst case is 650 calls. If most rows match near the top of the evaluation order (most advanced statuses), it will be much faster. Status mappings with blank JQL are skipped instantly.

**My JQL values disappeared after updating the script**  
Run `migrateFromOldSettings` from the Script Editor to move data from the old storage key (`statusMappings`) to the new key (`defaultStatusMappings`). Your data was never deleted.

---

## Script Properties Reference

The following keys are stored in Script Properties (visible in Script Editor → Project Settings → Script Properties):

| Key | Scope | Description |
|---|---|---|
| `jiraBaseUrl` | Global | JIRA instance URL |
| `authType` | Global | `basic` or `pat` |
| `customFieldStartDate` | Global | `customfield_19601` |
| `customFieldEndDate` | Global | `customfield_19602` |
| `headerJiraKey` etc. | Global | Column header names |
| `defaultStatusMappings` | Global | JSON array of `{label, jql}` objects |
| `scheduledTabs` | Global | JSON array of tab names in the daily schedule |
| `tab::[name]::jqlQuery` | Per-tab | Scope JQL for this tab |
| `tab::[name]::notifyEmails` | Per-tab | Notification addresses for this tab |
| `tab::[name]::statusMappings` | Per-tab | Optional JQL override for this tab |
| `pendingApproval` | Transient | Pending changes awaiting user approval (cleared after apply/cancel) |

JIRA credentials (`jiraUsername`, `jiraToken`) are stored in **User Properties** — they are private to each Google account and not visible to other editors of the sheet.
