const STATE_PROPERTY_KEY = 'syncState';

function loadState() {
  const raw = PropertiesService.getScriptProperties().getProperty(STATE_PROPERTY_KEY);
  if (!raw) return {};

  try {
    return JSON.parse(raw);
  } catch (e) {
    Logger.log('[JIRA Sync] Failed to parse state, resetting: ' + e.message);
    return {};
  }
}

function saveState(scopeIssues, keyToStatus) {
  const state = {};
  const now   = new Date().toISOString();

  scopeIssues.forEach(function(issue) {
    state[issue.key] = {
      status:        keyToStatus[issue.key] || 'Needs Review',
      startDate:     issue.startDate,
      targetEndDate: issue.targetEndDate,
      actualEndDate: issue.actualEndDate,
      syncedAt:      now
    };
  });

  PropertiesService.getScriptProperties()
    .setProperty(STATE_PROPERTY_KEY, JSON.stringify(state));
}

// Utility — call from Script Editor if you need to force a full re-sync
function clearState() {
  PropertiesService.getScriptProperties().deleteProperty(STATE_PROPERTY_KEY);
  Logger.log('[JIRA Sync] State cleared.');
}
