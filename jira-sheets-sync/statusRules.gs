// Runs each status mapping's JQL against JIRA and builds a key -> label map.
// scopeKeys limits every query to only the issues already known to be in scope,
// which prevents JIRA from traversing the full project hierarchy on each call.
// Evaluation stops early once every scope issue has been classified.
function classifyIssues(statusMappings, config, scopeKeys) {
  const keyToStatus  = {};
  const unclassified = {};
  scopeKeys.forEach(function(k) { unclassified[k] = true; });

  // Wrap the caller's JQL to restrict results to scope keys only.
  // This turns expensive project-wide parentsOf() scans into targeted lookups.
  const scopeFilter = 'key in (' + scopeKeys.join(',') + ')';

  for (var i = 0; i < statusMappings.length; i++) {
    var mapping = statusMappings[i];
    if (!mapping.jql || !mapping.jql.trim()) continue; // skip blank rows

    // Stop once every scope issue has a status
    if (Object.keys(unclassified).length === 0) break;

    var scopedJql = '(' + mapping.jql + ') AND ' + scopeFilter;

    try {
      var keys = fetchKeysByJql(scopedJql, config);
      keys.forEach(function(key) {
        if (!keyToStatus[key]) {
          keyToStatus[key] = mapping.label;
          delete unclassified[key];
        }
      });
    } catch (e) {
      throw new Error('JQL error in status mapping "' + mapping.label + '": ' + e.message);
    }
  }

  return keyToStatus;
}
