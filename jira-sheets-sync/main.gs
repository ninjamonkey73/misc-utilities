const DEFAULT_STATUS_MAPPINGS = [
  { label: 'Not Started',      jql: '' },
  { label: 'Researching',      jql: '' },
  { label: 'Researched',       jql: '' },
  { label: 'Designing',        jql: '' },
  { label: 'Designed',         jql: '' },
  { label: 'Coding',           jql: '' },
  { label: 'Code PR',          jql: '' },
  { label: 'Code PR Complete', jql: '' },
  { label: 'Test Planning',    jql: '' },
  { label: 'Testing',          jql: '' },
  { label: 'QC PR',            jql: '' },
  { label: 'Tested',           jql: '' },
  { label: 'Complete',         jql: '' }
];

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('JIRA Sync')
    .addItem('Run Now',  'runSync')
    .addSeparator()
    .addItem('Settings', 'openSettingsDialog')
    .addItem('Add This Tab to Daily Schedule', 'setupDailyTrigger')
    .addToUi();
}

// Loads global settings merged with per-tab overrides.
// tabName is optional; omit for global-only access.
function loadConfig(tabName) {
  const sp     = PropertiesService.getScriptProperties().getProperties();
  const up     = PropertiesService.getUserProperties().getProperties();
  const prefix = tabName ? 'tab::' + tabName + '::' : '';

  let statusMappings;
  // Per-tab override
  if (tabName && sp[prefix + 'statusMappings']) {
    try { statusMappings = JSON.parse(sp[prefix + 'statusMappings']); } catch(e) {}
  }
  // New global key
  if (!statusMappings && sp.defaultStatusMappings) {
    try { statusMappings = JSON.parse(sp.defaultStatusMappings); } catch(e) {}
  }
  // Fallback: old key from pre-migration design
  if (!statusMappings && sp.statusMappings) {
    try { statusMappings = JSON.parse(sp.statusMappings); } catch(e) {}
  }
  statusMappings = statusMappings || DEFAULT_STATUS_MAPPINGS;

  return {
    jiraBaseUrl:          sp.jiraBaseUrl              || '',
    authType:             sp.authType                 || 'basic',
    customFieldStartDate: sp.customFieldStartDate     || 'customfield_19601',
    customFieldEndDate:   sp.customFieldEndDate       || 'customfield_19602',
    headerJiraKey:        sp.headerJiraKey            || 'JIRA',
    headerStatus:         sp.headerStatus             || 'Status',
    headerStartDate:      sp.headerStartDate          || 'Target Start Date',
    headerEndDate:        sp.headerEndDate            || 'Target End Date',
    headerResolvedDate:   sp.headerResolvedDate       || 'Actual End Date',
    tabName:              tabName || '',
    jqlQuery:             sp[prefix + 'jqlQuery']     || '',
    notifyEmails:         sp[prefix + 'notifyEmails'] || '',
    statusMappings:       statusMappings,
    jiraUsername:         up.jiraUsername             || '',
    jiraToken:            up.jiraToken                || ''
  };
}

// Manual "Run Now" — uses the active sheet tab, shows approval dialog
function runSync() {
  const tabName = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet().getName();
  runSyncInternal_(tabName, false);
}

// Daily trigger — runs all scheduled tabs directly (no approval dialog)
function runSyncScheduled() {
  let scheduledTabs;
  try {
    scheduledTabs = JSON.parse(
      PropertiesService.getScriptProperties().getProperty('scheduledTabs') || '[]'
    );
  } catch(e) { scheduledTabs = []; }

  scheduledTabs.forEach(function(tabName) {
    try {
      runSyncInternal_(tabName, true);
    } catch(e) {
      Logger.log('Error syncing tab "' + tabName + '": ' + e.message + '\n' + e.stack);
    }
  });
}

function runSyncInternal_(tabName, triggeredBySchedule) {
  const config = loadConfig(tabName);

  if (!config.jiraBaseUrl || !config.jiraToken ||
      (config.authType !== 'pat' && !config.jiraUsername)) {
    if (triggeredBySchedule) {
      // Scheduled triggers run as the trigger owner — if their credentials are
      // missing from User Properties, log clearly so the trigger owner knows.
      Logger.log(
        '[JIRA Sync] Scheduled run for tab "' + tabName + '" failed: ' +
        'JIRA credentials not found for the trigger owner account. ' +
        'Open Settings on this sheet and save your credentials while signed in as the trigger owner.'
      );
    } else {
      openSettingsDialog();
    }
    return;
  }

  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) {
    if (!triggeredBySchedule) {
      SpreadsheetApp.getActiveSpreadsheet()
        .toast('Another sync is already running. Try again in a moment.', 'JIRA Sync', 5);
    }
    return;
  }

  try {
    const ss    = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(tabName);

    if (!sheet) {
      if (!triggeredBySchedule) {
        SpreadsheetApp.getUi().alert(
          'Sheet tab "' + tabName + '" not found. Check Settings.'
        );
      }
      return;
    }

    const pending = computePendingChanges_(sheet, config);

    if (triggeredBySchedule) {
      if (pending.changes.length > 0) writeChangesToSheet(pending.changes, sheet);
      sendDigestEmail(
        pending.changes, pending.newItems, pending.missingItems,
        pending.unclassified, config, true
      );
    } else {
      const hasContent = pending.changes.length > 0   || pending.newItems.length > 0 ||
                         pending.missingItems.length > 0 || pending.unclassified.length > 0;
      if (!hasContent) {
        ss.toast('No changes detected for tab "' + tabName + '".', 'JIRA Sync', 4);
        return;
      }
      PropertiesService.getScriptProperties()
        .setProperty('pendingApproval', JSON.stringify(pending));
      openApprovalDialog();
    }

  } catch(e) {
    Logger.log('JIRA Sync error: ' + e.message + '\n' + e.stack);
    if (!triggeredBySchedule) SpreadsheetApp.getUi().alert('Sync failed: ' + e.message);
  } finally {
    lock.releaseLock();
  }
}

// Computes all proposed changes without writing anything to the sheet.
function computePendingChanges_(sheet, config) {
  const cols    = resolveColumns(sheet, config);
  const keyToRow = buildKeyMap(sheet, cols);

  const scopeItems  = fetchScopeKeys(config);
  const scopeKeySet = {};
  scopeItems.forEach(function(s) { scopeKeySet[s.key] = s.summary; });

  const sheetKeys = Object.keys(keyToRow);

  const newItems = scopeItems.filter(function(s) { return !keyToRow[s.key]; });
  const missingItems = sheetKeys
    .filter(function(k) { return !scopeKeySet[k]; })
    .map(function(k) {
      return { key: k, row: keyToRow[k].row, lastStatus: keyToRow[k].currentStatus || 'Unknown' };
    });

  const changes      = [];
  const unclassified = [];

  sheetKeys.forEach(function(key) {
    if (!scopeKeySet[key]) return;

    const cell         = keyToRow[key];
    const cellIsManual = MANUAL_STATUSES.indexOf(cell.currentStatus) !== -1;
    const issue        = fetchIssueDetails(key, config);
    const status       = classifyIssue(key, issue.jiraStatus, config.statusMappings, config);

    if (cellIsManual && status !== 'Complete') return;

    const fieldEdits = [];

    if (!status) {
      unclassified.push({ key: key, summary: issue.summary });
    } else if (status !== cell.currentStatus) {
      fieldEdits.push({ col: cols.colStatus, value: status, field: 'status',
                        prevValue: cell.currentStatus });
    }
    if (issue.startDate && issue.startDate !== cell.currentStart) {
      fieldEdits.push({ col: cols.colStart, value: issue.startDate, field: 'startDate',
                        prevValue: cell.currentStart });
    }
    if (issue.targetEndDate && issue.targetEndDate !== cell.currentEnd) {
      fieldEdits.push({ col: cols.colEnd, value: issue.targetEndDate, field: 'targetEndDate',
                        prevValue: cell.currentEnd });
    }
    if (issue.actualEndDate && issue.actualEndDate !== cell.currentResolved) {
      fieldEdits.push({ col: cols.colResolved, value: issue.actualEndDate, field: 'actualEndDate',
                        prevValue: cell.currentResolved });
    }

    if (fieldEdits.length > 0) {
      changes.push({ key: key, summary: issue.summary, row: cell.row, fields: fieldEdits });
    }
  });

  return { tabName: config.tabName, changes: changes, newItems: newItems,
           missingItems: missingItems, unclassified: unclassified };
}

// Adds the active tab to the scheduled tabs list and sets up the trigger if needed.
function setupDailyTrigger() {
  const tabName = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet().getName();
  const sp      = PropertiesService.getScriptProperties();

  let scheduledTabs;
  try { scheduledTabs = JSON.parse(sp.getProperty('scheduledTabs') || '[]'); } catch(e) { scheduledTabs = []; }

  if (scheduledTabs.indexOf(tabName) === -1) {
    scheduledTabs.push(tabName);
    sp.setProperty('scheduledTabs', JSON.stringify(scheduledTabs));
  }

  const hasTimeTrigger = ScriptApp.getProjectTriggers().some(function(t) {
    return t.getHandlerFunction() === 'runSyncScheduled';
  });
  if (!hasTimeTrigger) {
    ScriptApp.newTrigger('runSyncScheduled').timeBased().everyDays(1).atHour(8).create();
  }

  SpreadsheetApp.getActiveSpreadsheet()
    .toast('"' + tabName + '" added to daily sync at 8 AM.', 'JIRA Sync', 4);
}
