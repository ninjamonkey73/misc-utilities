// Runs each status mapping's JQL against JIRA and builds a key → label map.
// Evaluation is ordered — first match wins, so BLOCKED/HOLD at positions 0/1
// take priority over all workflow statuses.
function classifyIssues(statusMappings, config) {
  const keyToStatus = {};

  statusMappings.forEach(function(mapping) {
    if (!mapping.jql || !mapping.jql.trim()) return; // skip blank rows

    const keys = fetchKeysByJql(mapping.jql, config);
    keys.forEach(function(key) {
      if (!keyToStatus[key]) {
        keyToStatus[key] = mapping.label;
      }
    });
  });

  return keyToStatus;
}
