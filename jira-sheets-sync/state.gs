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

// ── Distribution / template utilities ───────────────────────────────────────

// Generates the JavaScript code for DEFAULT_STATUS_MAPPINGS using your current
// saved JQL values. Run from the Script Editor, then copy the logged output and
// replace the DEFAULT_STATUS_MAPPINGS constant in main.gs so new sheet copies
// start pre-loaded without any manual JQL entry.
function generateDefaultMappingsCode() {
  const sp = PropertiesService.getScriptProperties();

  let mappings;
  try { mappings = JSON.parse(sp.getProperty('defaultStatusMappings') || ''); } catch(e) {}
  if (!mappings) {
    try { mappings = JSON.parse(sp.getProperty('statusMappings') || ''); } catch(e) {}
  }
  if (!mappings || !mappings.length) {
    Logger.log('No status mappings found in Script Properties. Configure them in Settings first.');
    return;
  }

  var lines = ['const DEFAULT_STATUS_MAPPINGS = ['];
  mappings.forEach(function(m, i) {
    var jqlEscaped = (m.jql || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
    var comma = i < mappings.length - 1 ? ',' : '';
    lines.push("  { label: '" + m.label + "', jql: '" + jqlEscaped + "' }" + comma);
  });
  lines.push('];');

  Logger.log('=== Paste this into main.gs to replace DEFAULT_STATUS_MAPPINGS ===\n\n' +
             lines.join('\n') + '\n\n=== End of generated code ===');
}

// ── Migration / recovery utilities ──────────────────────────────────────────

// Migrates settings from the old single-tab design to the new global/per-tab design.
// Run once from the Script Editor after upgrading to the new version.
// Safe to run multiple times — only writes if the new keys are not already set.
function migrateFromOldSettings() {
  const sp = PropertiesService.getScriptProperties();
  const all = sp.getProperties();

  Logger.log('=== Old Script Properties ===');
  Object.keys(all).forEach(function(k) {
    Logger.log(k + ' = ' + (k === 'jiraToken' ? '(hidden)' : all[k]));
  });

  // Migrate status mappings: old key = 'statusMappings', new key = 'defaultStatusMappings'
  if (all.statusMappings && !all.defaultStatusMappings) {
    sp.setProperty('defaultStatusMappings', all.statusMappings);
    Logger.log('Migrated statusMappings → defaultStatusMappings');
  } else if (all.statusMappings) {
    Logger.log('defaultStatusMappings already set — skipped mapping migration');
    Logger.log('Old statusMappings value (for reference): ' + all.statusMappings);
  }

  // Migrate tab-level JQL: old key = 'jqlQuery', new key = 'tab::[tabName]::jqlQuery'
  // Requires knowing the tab name — reads from old 'tabName' key if present
  if (all.jqlQuery) {
    const tabName = all.tabName || '';
    if (tabName) {
      const tabKey = 'tab::' + tabName + '::jqlQuery';
      if (!all[tabKey]) {
        sp.setProperty(tabKey, all.jqlQuery);
        Logger.log('Migrated jqlQuery → ' + tabKey);
      } else {
        Logger.log(tabKey + ' already set — skipped JQL migration');
      }
    } else {
      Logger.log('Old jqlQuery found but no tabName set — cannot migrate automatically.');
      Logger.log('Old jqlQuery value: ' + all.jqlQuery);
      Logger.log('Manually set it via Settings → Tab panel after opening the correct sheet tab.');
    }
  }

  // Migrate notification emails similarly
  if (all.notifyEmails) {
    const tabName = all.tabName || '';
    if (tabName) {
      const tabKey = 'tab::' + tabName + '::notifyEmails';
      if (!all[tabKey]) {
        sp.setProperty(tabKey, all.notifyEmails);
        Logger.log('Migrated notifyEmails → ' + tabKey);
      }
    }
  }

  Logger.log('=== Migration complete. Check Execution Log for details. ===');
}
