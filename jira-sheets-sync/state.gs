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

// Utility — call from Script Editor to force a full re-sync on next run
function clearState() {
  PropertiesService.getScriptProperties().deleteProperty(STATE_PROPERTY_KEY);
  Logger.log('[JIRA Sync] State cleared.');
}
