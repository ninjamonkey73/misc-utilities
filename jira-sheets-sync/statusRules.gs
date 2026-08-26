// Separate patterns for double-quoted and single-quoted parentsOf arguments.
// A combined ["'] pattern stops at the first inner quote of either type,
// which truncates the inner JQL when it contains single-quoted status values
// like 'Peer Review' inside a double-quoted parentsOf("...") call.
var PARENTS_OF_DQ = /issueFunction\s+in\s+parentsOf\s*\(\s*"([\s\S]*?)"\s*\)/i;
var PARENTS_OF_SQ = /issueFunction\s+in\s+parentsOf\s*\(\s*'([\s\S]*?)'\s*\)/i;

// Returns { innerJql, pattern } if jql contains a parentsOf call, else null.
function getParentsOfMatch_(jql) {
  var m = jql.match(PARENTS_OF_DQ);
  if (m) return { innerJql: m[1], pattern: PARENTS_OF_DQ };
  m = jql.match(PARENTS_OF_SQ);
  if (m) return { innerJql: m[1], pattern: PARENTS_OF_SQ };
  return null;
}

// Classifies a single JIRA issue by evaluating each status mapping in priority order.
// Stops at the first match and returns the label, or null if nothing matched.
//
// issueStatus: the parent issue's current JIRA status name (from fetchIssueDetails).
// Used to short-circuit parent-status checks without an extra API call.
function classifyIssue(key, issueStatus, statusMappings, config) {
  for (var i = 0; i < statusMappings.length; i++) {
    var mapping = statusMappings[i];
    if (!mapping.jql || !mapping.jql.trim()) continue;

    var matched;
    try {
      matched = evaluateRule_(key, issueStatus, mapping.jql, config);
    } catch (e) {
      throw new Error('JQL error in status mapping "' + mapping.label + '": ' + e.message);
    }

    if (matched) return mapping.label;
  }

  return null;
}

// Evaluates one status rule against a specific issue.
//
// For rules containing issueFunction in parentsOf("inner") or parentsOf('inner'):
//   1. Extracts the parent-level condition (e.g. status = "In Progress")
//   2. Checks it locally against issueStatus — no API call if it fails fast
//   3. Rewrites to: parent = KEY AND (inner_jql) — only checks that issue's subtasks
//
// For all other rules: runs (jql) AND key = KEY.
function evaluateRule_(key, issueStatus, jql, config) {
  var pof = getParentsOfMatch_(jql);

  if (pof) {
    // Extract the parent-level condition (everything before issueFunction in parentsOf(...))
    var parentCondition = jql.replace(pof.pattern, '')
                             .replace(/\s*AND\s*$/i, '')
                             .replace(/^\s*AND\s*/i, '')
                             .trim();

    // If there is a simple parent status condition, check it locally before hitting JIRA
    if (parentCondition) {
      var statusMatch = parentCondition.match(/^status\s*=\s*["']?([^"',\)]+?)["']?\s*$/i);
      if (statusMatch) {
        var requiredStatus = statusMatch[1].trim();
        if (issueStatus !== requiredStatus) {
          return false; // fast reject — no API call needed
        }
      }
    }

    // Rewrite parentsOf to a targeted subtask check: only looks at this issue's children
    var subtaskJql = 'parent = ' + key + ' AND (' + pof.innerJql + ')';
    return checkJqlHasResults_(subtaskJql, config);
  }

  // No parentsOf detected — run as a direct key-filtered query
  return checkJqlHasResults_('(' + jql + ') AND key = ' + key, config);
}

// Returns true if the given JQL matches at least one issue.
function checkJqlHasResults_(jql, config) {
  var data = jiraRequest_(config, '/rest/api/2/search', {
    jql:        jql,
    fields:     'key',
    maxResults: 1
  });
  return (data.total || 0) > 0;
}
