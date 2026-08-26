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

// Full scope fetch — returns all issues matching the main JQL with date fields
function fetchScopeIssues(config) {
  const fields = [
    'key',
    'summary',
    config.customFieldStartDate,
    config.customFieldEndDate,
    'resolutiondate'
  ].join(',');

  const allIssues = [];
  let startAt = 0;

  do {
    const data = jiraRequest_(config, '/rest/api/2/search', {
      jql:        config.jqlQuery,
      fields:     fields,
      maxResults: 100,
      startAt:    startAt
    });

    // Log field keys on first page to verify customfield suffix (-val or not)
    if (startAt === 0 && data.issues && data.issues.length > 0) {
      Logger.log('[JIRA Sync] Sample issue field keys: ' +
        JSON.stringify(Object.keys(data.issues[0].fields)));
    }

    (data.issues || []).forEach(function(issue) {
      allIssues.push(parseIssue_(issue, config));
    });

    startAt += 100;
    if (startAt >= (data.total || 0)) break;
  } while (true);

  return allIssues;
}

function parseIssue_(issue, config) {
  const f = issue.fields;

  // Handle potential -val suffix returned by some JIRA DC instances
  const startDate = f[config.customFieldStartDate] ||
                    f[config.customFieldStartDate + '-val'] || null;
  const endDate   = f[config.customFieldEndDate]   ||
                    f[config.customFieldEndDate   + '-val'] || null;

  return {
    key:           issue.key,
    summary:       f.summary || '',
    startDate:     startDate     ? String(startDate).substring(0, 10)     : null,
    targetEndDate: endDate       ? String(endDate).substring(0, 10)       : null,
    actualEndDate: f.resolutiondate ? String(f.resolutiondate).substring(0, 10) : null
  };
}

// Lightweight key-only fetch for a single swimlane JQL
function fetchKeysByJql(jql, config) {
  if (!jql || !jql.trim()) return [];

  const keys = [];
  let startAt = 0;

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

// maxResults=0 trick: JIRA returns total count without fetching any records
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
