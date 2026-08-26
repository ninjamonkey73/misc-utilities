function jiraRequest_(config, path, params) {
  const qs = params
    ? '?' + Object.keys(params).map(function(k) {
        return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]);
      }).join('&')
    : '';

  const url = config.jiraBaseUrl.replace(/\/$/, '') + path + qs;

  const authHeader = (config.authType === 'pat')
    ? 'Bearer ' + config.jiraToken
    : 'Basic ' + Utilities.base64Encode(config.jiraUsername + ':' + config.jiraToken);

  const response = UrlFetchApp.fetch(url, {
    method: 'GET',
    headers: {
      'Authorization': authHeader,
      'Content-Type':  'application/json'
    },
    muteHttpExceptions: true
  });

  const code = response.getResponseCode();
  const text = response.getContentText();

  if (code === 401) throw new Error('JIRA authentication failed (401). Check credentials in Settings.');
  if (code === 403) throw new Error(
    'JIRA returned 403 Forbidden. Common causes:\n' +
    '• Auth type mismatch — if using a Personal Access Token, set Auth Type to "PAT (Bearer)" in Settings.\n' +
    '• Your account lacks Browse permission for the project in your JQL.\n' +
    '• Basic Auth may be disabled on this JIRA instance (SSO/SAML only).'
  );
  if (code === 400) throw new Error('Bad JIRA request: ' + text);
  if (code < 200 || code >= 300) throw new Error('JIRA API error ' + code + ': ' + text);

  return JSON.parse(text);
}

// Pass 1: fetch only keys + summaries from the scope JQL.
// Used for new/missing detection only — does NOT fetch date fields.
function fetchScopeKeys(config) {
  const items  = [];
  let startAt  = 0;

  do {
    const data = jiraRequest_(config, '/rest/api/2/search', {
      jql:        config.jqlQuery,
      fields:     'key,summary',
      maxResults: 100,
      startAt:    startAt
    });

    (data.issues || []).forEach(function(issue) {
      items.push({ key: issue.key, summary: (issue.fields || {}).summary || '' });
    });

    startAt += 100;
    if (startAt >= (data.total || 0)) break;
  } while (true);

  return items; // array of { key, summary }
}

// Pass 2: fetch full details for one specific issue (status + date fields).
function fetchIssueDetails(key, config) {
  const fieldsList = [
    'key',
    'summary',
    'status',
    config.customFieldStartDate,
    config.customFieldEndDate,
    'resolutiondate'
  ].join(',');

  const data = jiraRequest_(config, '/rest/api/2/issue/' + encodeURIComponent(key), {
    fields: fieldsList
  });

  return parseIssue_(data, config);
}

function parseIssue_(issue, config) {
  const f = issue.fields || {};

  // Handle potential -val suffix returned by some JIRA DC instances
  const startDate = f[config.customFieldStartDate] ||
                    f[config.customFieldStartDate + '-val'] || null;
  const endDate   = f[config.customFieldEndDate]   ||
                    f[config.customFieldEndDate   + '-val'] || null;

  return {
    key:           issue.key,
    summary:       f.summary || '',
    jiraStatus:    (f.status && f.status.name) ? f.status.name : '',
    startDate:     startDate        ? String(startDate).substring(0, 10)        : null,
    targetEndDate: endDate          ? String(endDate).substring(0, 10)          : null,
    actualEndDate: f.resolutiondate ? String(f.resolutiondate).substring(0, 10) : null
  };
}

// Check whether a single issue key matches a given JQL.
// Uses maxResults=0 — JIRA returns total without fetching any records.
function checkIssueMatchesJql(key, jql, config) {
  if (!jql || !jql.trim()) return false;

  const data = jiraRequest_(config, '/rest/api/2/search', {
    jql:        '(' + jql + ') AND key = ' + key,
    fields:     'key',
    maxResults: 0
  });

  return (data.total || 0) > 0;
}

// Kept for the Test button in the settings dialog.
function testJqlCount(jql, config) {
  if (!jql || !jql.trim()) return { count: 0, error: null };

  try {
    const data = jiraRequest_(config, '/rest/api/2/search', {
      jql:        jql,
      fields:     'key',
      maxResults: 0
    });
    return { count: data.total || 0, error: null };
  } catch (e) {
    return { count: 0, error: e.message };
  }
}

// Generic paginated key fetch — used by testJqlCount path only.
function fetchKeysByJql(jql, config) {
  if (!jql || !jql.trim()) return [];

  const keys   = [];
  let startAt  = 0;

  do {
    const data = jiraRequest_(config, '/rest/api/2/search', {
      jql:        jql,
      fields:     'key',
      maxResults: 500,
      startAt:    startAt
    });

    (data.issues || []).forEach(function(issue) { keys.push(issue.key); });
    startAt += 500;
    if (startAt >= (data.total || 0)) break;
  } while (true);

  return keys;
}
