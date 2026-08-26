
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
    .addItem('Run Now', 'runSync')
    .addSeparator()
    .addItem('Settings', 'openSettingsDialog')
    .addItem('Set Up Daily Trigger', 'setupDailyTrigger')
    .addToUi();
}

function loadConfig() {
  const sp = PropertiesService.getScriptProperties().getProperties();
  const up = PropertiesService.getUserProperties().getProperties();

  let statusMappings;
  try {
    statusMappings = sp.statusMappings ? JSON.parse(sp.statusMappings) : DEFAULT_STATUS_MAPPINGS;
  } catch (e) {
    statusMappings = DEFAULT_STATUS_MAPPINGS;
  }

  return {
    jiraBaseUrl:          sp.jiraBaseUrl              || '',
    jqlQuery:             sp.jqlQuery                 || '',
    tabName:              sp.tabName                  || '',
    statusMappings:       statusMappings,
    authType:             sp.authType                 || 'basic',
    customFieldStartDate: sp.customFieldStartDate     || 'customfield_19601',
    customFieldEndDate:   sp.customFieldEndDate       || 'customfield_19602',
    notifyEmails:         sp.notifyEmails             || '',
    headerJiraKey:        sp.headerJiraKey            || 'JIRA',
    headerStatus:         sp.headerStatus             || 'Status',
    headerStartDate:      sp.headerStartDate          || 'Target Start Date',
    headerEndDate:        sp.headerEndDate            || 'Target End Date',
    headerResolvedDate:   sp.headerResolvedDate       || 'Actual End Date',
    jiraUsername:         up.jiraUsername             || '',
    jiraToken:            up.jiraToken                || ''
  };
}

// Entry point for manual "Run Now" menu click
function runSync() {
  runSyncInternal(false);
}

// Entry point for the daily time-based trigger
function runSyncScheduled() {
  runSyncInternal(true);
}

function runSyncInternal(triggeredBySchedule) {
  const config = loadConfig();

  // First-run guard: open settings if credentials or base URL are missing
  if (!config.jiraBaseUrl || !config.jiraUsername || !config.jiraToken) {
    if (!triggeredBySchedule) {
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
    const sheet = ss.getSheetByName(config.tabName);

    if (!sheet) {
      if (!triggeredBySchedule) {
        SpreadsheetApp.getUi().alert('Sheet tab "' + config.tabName + '" not found. Check Settings.');
      }
      return;
    }

    const cols     = resolveColumns(sheet, config); // finds columns by header name
    const keyToRow = buildKeyMap(sheet, cols);

    // ── PASS 1: scope fetch (keys + summaries only) for new/missing detection ──
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

    // ── PASS 2: per-row status classification + date fetch ──
    // Ground truth is always the current cell values — no state dependency.
    const changes     = [];
    const unclassified = [];

    sheetKeys.forEach(function(key) {
      if (!scopeKeySet[key]) return; // missing item — skip

      const cell = keyToRow[key];

      // Freeze rows where a human has typed BLOCKED or HOLD.
      // Only Complete overrides the freeze — no other automated status can clear it.
      const cellIsManual = MANUAL_STATUSES.indexOf(cell.currentStatus) !== -1;

      // Fetch issue details (JIRA status + date fields)
      const issue  = fetchIssueDetails(key, config);

      // Classify status; issue.jiraStatus short-circuits parent conditions locally
      const status = classifyIssue(key, issue.jiraStatus, config.statusMappings, config);

      if (cellIsManual && status !== 'Complete') return; // frozen

      const fieldEdits = [];

      if (!status) {
        unclassified.push({ key: key, summary: issue.summary });
      } else if (status !== cell.currentStatus) {
        fieldEdits.push({ col: cols.colStatus, value: status, field: 'status',
                          prevValue: cell.currentStatus });
      }

      // Date fields: only write when JIRA has a value and it differs from the cell.
      // Empty JIRA fields are ignored — preserves manually entered dates.
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
        changes.push({
          key:     key,
          summary: issue.summary,
          row:     cell.row,
          fields:  fieldEdits
        });
      }
    });

    if (changes.length > 0) writeChangesToSheet(changes, sheet);

    sendDigestEmail(changes, newItems, missingItems, unclassified, config, triggeredBySchedule);

    if (!triggeredBySchedule) {
      ss.toast(
        'Sync complete — ' + changes.length + ' change(s). Open "JIRA Sync → Settings" to reconfigure.',
        'JIRA Sync',
        8
      );
    }
  } catch (e) {
    Logger.log('JIRA Sync error: ' + e.message + '\n' + e.stack);
    if (!triggeredBySchedule) {
      SpreadsheetApp.getUi().alert('Sync failed: ' + e.message);
    }
  } finally {
    lock.releaseLock();
  }
}

function setupDailyTrigger() {
  ScriptApp.getProjectTriggers().forEach(function(t) {
    if (t.getHandlerFunction() === 'runSyncScheduled') ScriptApp.deleteTrigger(t);
  });

  ScriptApp.newTrigger('runSyncScheduled')
    .timeBased()
    .everyDays(1)
    .atHour(8)
    .create();

  SpreadsheetApp.getActiveSpreadsheet()
    .toast('Daily trigger set for 8 AM.', 'JIRA Sync', 4);
}
