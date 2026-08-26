// Reads the JIRA key column and returns a map of key → 1-based row index
function buildKeyMap(sheet) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return {};

  const values = sheet.getRange(2, COL_JIRA_KEY, lastRow - 1, 1).getValues();
  const map    = {};

  values.forEach(function(row, i) {
    const key = String(row[0] || '').trim();
    if (key) map[key] = i + 2;
  });

  return map;
}

const MANUAL_STATUSES = ['BLOCKED', 'HOLD'];

// Compares current JIRA data against prior state and the sheet key map.
// Returns three lists: field-level changes, new JIRA issues with no sheet row,
// and sheet rows whose JIRA key was absent from the scope fetch.
function detectChanges(scopeIssues, keyToStatus, keyToRow, state) {
  const changes      = [];
  const newItems     = [];
  const missingItems = [];
  const scopeKeySet  = {};

  scopeIssues.forEach(function(issue) {
    scopeKeySet[issue.key] = true;

    if (!keyToRow[issue.key]) {
      newItems.push(issue);
      return;
    }

    const prev   = state[issue.key] || {};
    const status = keyToStatus[issue.key] || 'Needs Review';
    const row    = keyToRow[issue.key];

    // BLOCKED and HOLD are human-set designations. Skip all updates for these
    // rows unless the story has reached Complete, in which case it overrides.
    const isManuallyFlagged = MANUAL_STATUSES.indexOf(prev.status) !== -1;
    if (isManuallyFlagged && status !== 'Complete') return;

    const fieldEdits = [];

    if (status !== prev.status) {
      fieldEdits.push({ col: COL_STATUS, value: status, field: 'status' });
    }
    // Only write date fields when JIRA has a non-null value — preserves
    // manually entered dates for teams not using JIRA date fields
    if (issue.startDate && issue.startDate !== prev.startDate) {
      fieldEdits.push({ col: COL_START, value: issue.startDate, field: 'startDate' });
    }
    if (issue.targetEndDate && issue.targetEndDate !== prev.targetEndDate) {
      fieldEdits.push({ col: COL_END, value: issue.targetEndDate, field: 'targetEndDate' });
    }
    if (issue.actualEndDate && issue.actualEndDate !== prev.actualEndDate) {
      fieldEdits.push({ col: COL_RESOLVED, value: issue.actualEndDate, field: 'actualEndDate' });
    }

    if (fieldEdits.length > 0) {
      changes.push({
        key:     issue.key,
        summary: issue.summary,
        row:     row,
        prev:    prev,
        current: {
          status:        status,
          startDate:     issue.startDate,
          targetEndDate: issue.targetEndDate,
          actualEndDate: issue.actualEndDate
        },
        fields: fieldEdits
      });
    }
  });

  // Sheet rows whose key wasn't in the JIRA scope results
  Object.keys(keyToRow).forEach(function(key) {
    if (!scopeKeySet[key]) {
      missingItems.push({
        key:        key,
        row:        keyToRow[key],
        lastStatus: (state[key] || {}).status || 'Unknown'
      });
    }
  });

  return { changes: changes, newItems: newItems, missingItems: missingItems };
}

function writeChangesToSheet(changes, sheet) {
  changes.forEach(function(change) {
    change.fields.forEach(function(fc) {
      sheet.getRange(change.row, fc.col).setValue(fc.value);
    });
  });
}
