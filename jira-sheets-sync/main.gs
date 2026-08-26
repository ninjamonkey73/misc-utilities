// Column indices (1-based, matching confirmed sheet layout)
const COL_JIRA_KEY = 6;  // F
const COL_STATUS   = 9;  // I
const COL_START    = 11; // K
const COL_END      = 12; // L
const COL_RESOLVED = 13; // M

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

    const scopeIssues  = fetchScopeIssues(config);
    const keyToStatus  = classifyIssues(config.statusMappings, config);
    const keyToRow     = buildKeyMap(sheet);
    const state        = loadState();

    const { changes, newItems, missingItems } = detectChanges(
      scopeIssues, keyToStatus, keyToRow, state
    );

    if (changes.length > 0) {
      writeChangesToSheet(changes, sheet);
      saveState(scopeIssues, keyToStatus);
    }

    sendDigestEmail(changes, newItems, missingItems, config, triggeredBySchedule);

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
