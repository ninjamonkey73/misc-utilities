const EXCLUDED_LABELS = ['BLOCKED', 'HOLD'];

// ── Settings dialog ──────────────────────────────────────────────────────────

function openSettingsDialog() {
  const html = HtmlService
    .createHtmlOutputFromFile('settings')
    .setWidth(660)
    .setHeight(720);
  SpreadsheetApp.getUi().showModalDialog(html, 'JIRA Sync — Settings');
}

// Called by the settings dialog on load.
// Returns global settings + per-tab settings for the active sheet tab.
function getSettingsForDialog() {
  const tabName = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet().getName();
  const sp      = PropertiesService.getScriptProperties().getProperties();
  const up      = PropertiesService.getUserProperties().getProperties();
  const prefix  = 'tab::' + tabName + '::';

  let defaultMappings;
  try { defaultMappings = JSON.parse(sp.defaultStatusMappings); } catch(e) {}
  defaultMappings = (defaultMappings || DEFAULT_STATUS_MAPPINGS).filter(function(m) {
    return EXCLUDED_LABELS.indexOf(m.label) === -1;
  });

  let tabMappings = null;
  if (sp[prefix + 'statusMappings']) {
    try { tabMappings = JSON.parse(sp[prefix + 'statusMappings']); } catch(e) {}
    if (tabMappings) tabMappings = tabMappings.filter(function(m) {
      return EXCLUDED_LABELS.indexOf(m.label) === -1;
    });
  }

  let scheduledTabs;
  try { scheduledTabs = JSON.parse(sp.scheduledTabs || '[]'); } catch(e) { scheduledTabs = []; }

  return {
    // Global
    jiraBaseUrl:        sp.jiraBaseUrl        || '',
    authType:           sp.authType           || 'basic',
    jiraUsername:       up.jiraUsername       || '',
    jiraToken:          up.jiraToken          || '',
    headerJiraKey:      sp.headerJiraKey      || 'JIRA',
    headerStatus:       sp.headerStatus       || 'Status',
    headerStartDate:    sp.headerStartDate    || 'Target Start Date',
    headerEndDate:      sp.headerEndDate      || 'Target End Date',
    headerResolvedDate: sp.headerResolvedDate || 'Actual End Date',
    defaultMappings:    defaultMappings,
    // Per-tab
    tabName:            tabName,
    jqlQuery:           sp[prefix + 'jqlQuery']       || '',
    notifyEmails:       sp[prefix + 'notifyEmails']   || '',
    hasTabMappings:     tabMappings !== null,
    tabMappings:        tabMappings,
    isScheduled:        scheduledTabs.indexOf(tabName) !== -1
  };
}

// Called by the settings dialog on Save.
function saveSettingsFromDialog(formData) {
  const sp = PropertiesService.getScriptProperties();
  const up = PropertiesService.getUserProperties();

  // Global settings
  sp.setProperties({
    jiraBaseUrl:           formData.jiraBaseUrl        || '',
    authType:              formData.authType            || 'basic',
    headerJiraKey:         formData.headerJiraKey       || 'JIRA',
    headerStatus:          formData.headerStatus        || 'Status',
    headerStartDate:       formData.headerStartDate     || 'Target Start Date',
    headerEndDate:         formData.headerEndDate       || 'Target End Date',
    headerResolvedDate:    formData.headerResolvedDate  || 'Actual End Date',
    defaultStatusMappings: JSON.stringify(formData.defaultMappings || DEFAULT_STATUS_MAPPINGS),
    customFieldStartDate:  'customfield_19601',
    customFieldEndDate:    'customfield_19602'
  });

  // Per-tab settings
  const tabName = formData.tabName;
  const prefix  = 'tab::' + tabName + '::';
  sp.setProperty(prefix + 'jqlQuery',     formData.jqlQuery     || '');
  sp.setProperty(prefix + 'notifyEmails', formData.notifyEmails || '');

  if (formData.hasTabMappings && formData.tabMappings) {
    sp.setProperty(prefix + 'statusMappings', JSON.stringify(formData.tabMappings));
  } else {
    sp.deleteProperty(prefix + 'statusMappings');
  }

  // Scheduled tabs list
  let scheduledTabs;
  try { scheduledTabs = JSON.parse(sp.getProperty('scheduledTabs') || '[]'); } catch(e) { scheduledTabs = []; }
  const idx = scheduledTabs.indexOf(tabName);
  if (formData.isScheduled && idx === -1)  scheduledTabs.push(tabName);
  if (!formData.isScheduled && idx !== -1) scheduledTabs.splice(idx, 1);
  sp.setProperty('scheduledTabs', JSON.stringify(scheduledTabs));

  // Credentials (per-user)
  up.setProperties({
    jiraUsername: formData.jiraUsername || '',
    jiraToken:    formData.jiraToken    || ''
  });

  return { success: true };
}

// Called by Test ▶ buttons in the settings dialog.
function testJqlFromDialog(jql) {
  const tabName = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet().getName();
  const config  = loadConfig(tabName);
  const hasCredentials = config.jiraBaseUrl && config.jiraToken &&
    (config.authType === 'pat' || config.jiraUsername);
  if (!hasCredentials) {
    return { count: 0, error: 'Save your JIRA credentials before testing.' };
  }
  return testJqlCount(jql, config);
}

// ── Approval dialog ──────────────────────────────────────────────────────────

function openApprovalDialog() {
  const html = HtmlService
    .createHtmlOutputFromFile('approval')
    .setWidth(620)
    .setHeight(560);
  SpreadsheetApp.getUi().showModalDialog(html, 'JIRA Sync — Review Changes');
}

// Called by the approval dialog on load to retrieve pending changes.
function getPendingApproval() {
  const raw = PropertiesService.getScriptProperties().getProperty('pendingApproval');
  if (!raw) return null;
  return JSON.parse(raw);
}

// Called by the approval dialog's Apply button.
// approvedKeys: array of JIRA keys whose changes the user approved.
function applyApprovedChanges(approvedKeys) {
  const raw = PropertiesService.getScriptProperties().getProperty('pendingApproval');
  if (!raw) return { error: 'No pending changes found. The session may have expired.' };

  const pending = JSON.parse(raw);
  const config  = loadConfig(pending.tabName);
  const ss      = SpreadsheetApp.getActiveSpreadsheet();
  const sheet   = ss.getSheetByName(pending.tabName);

  if (!sheet) return { error: 'Sheet tab "' + pending.tabName + '" not found.' };

  const approvedSet = {};
  (approvedKeys || []).forEach(function(k) { approvedSet[k] = true; });
  const approved = pending.changes.filter(function(c) { return approvedSet[c.key]; });

  if (approved.length > 0) writeChangesToSheet(approved, sheet);

  sendDigestEmail(
    approved, pending.newItems, pending.missingItems, pending.unclassified, config, false
  );

  PropertiesService.getScriptProperties().deleteProperty('pendingApproval');

  return { success: true, count: approved.length };
}

// Called by the approval dialog's Cancel button.
function cancelApproval() {
  PropertiesService.getScriptProperties().deleteProperty('pendingApproval');
}
