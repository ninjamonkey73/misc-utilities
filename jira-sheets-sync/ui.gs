function openSettingsDialog() {
  const html = HtmlService
    .createHtmlOutputFromFile('settings')
    .setWidth(620)
    .setHeight(660);
  SpreadsheetApp.getUi().showModalDialog(html, 'JIRA Sync — Settings');
}

const EXCLUDED_LABELS = ['BLOCKED', 'HOLD'];

// Called by the settings dialog on load to pre-populate all fields
function getSettingsForDialog() {
  const config = loadConfig();
  return {
    jiraBaseUrl:        config.jiraBaseUrl,
    authType:           config.authType,
    jiraUsername:       config.jiraUsername,
    jiraToken:          config.jiraToken,
    jqlQuery:           config.jqlQuery,
    tabName:            config.tabName,
    notifyEmails:       config.notifyEmails,
    headerJiraKey:      config.headerJiraKey,
    headerStatus:       config.headerStatus,
    headerStartDate:    config.headerStartDate,
    headerEndDate:      config.headerEndDate,
    headerResolvedDate: config.headerResolvedDate,
    statusMappings:     config.statusMappings.filter(function(m) {
      return EXCLUDED_LABELS.indexOf(m.label) === -1;
    })
  };
}

// Called by the settings dialog on Save
function saveSettingsFromDialog(formData) {
  PropertiesService.getScriptProperties().setProperties({
    jiraBaseUrl:          formData.jiraBaseUrl        || '',
    authType:             formData.authType            || 'basic',
    jqlQuery:             formData.jqlQuery            || '',
    tabName:              formData.tabName             || '',
    notifyEmails:         formData.notifyEmails        || '',
    headerJiraKey:        formData.headerJiraKey       || 'JIRA',
    headerStatus:         formData.headerStatus        || 'Status',
    headerStartDate:      formData.headerStartDate     || 'Target Start Date',
    headerEndDate:        formData.headerEndDate       || 'Target End Date',
    headerResolvedDate:   formData.headerResolvedDate  || 'Actual End Date',
    statusMappings:       JSON.stringify(formData.statusMappings || DEFAULT_STATUS_MAPPINGS),
    customFieldStartDate: 'customfield_19601',
    customFieldEndDate:   'customfield_19602'
  });

  PropertiesService.getUserProperties().setProperties({
    jiraUsername: formData.jiraUsername || '',
    jiraToken:    formData.jiraToken    || ''
  });

  return { success: true };
}

// Called by each [Test ▶] button in the dialog
function testJqlFromDialog(jql) {
  const config = loadConfig();
  const hasCredentials = config.jiraBaseUrl && config.jiraToken &&
    (config.authType === 'pat' || config.jiraUsername);
  if (!hasCredentials) {
    return { count: 0, error: 'Save your JIRA credentials before testing.' };
  }
  return testJqlCount(jql, config);
}
