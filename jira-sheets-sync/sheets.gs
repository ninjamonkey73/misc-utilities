const MANUAL_STATUSES = ['BLOCKED', 'HOLD'];

// Reads row 1 of the sheet to find each managed column's index by header name.
// Throws a descriptive error if a required header is missing.
function resolveColumns(sheet, config) {
  const headerRow = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const headerMap = {};
  headerRow.forEach(function(h, i) {
    const name = String(h || '').trim();
    if (name) headerMap[name] = i + 1; // 1-based
  });

  function find(configKey, label) {
    const name = config[configKey];
    const col  = headerMap[name];
    if (!col) {
      throw new Error(
        'Column header "' + name + '" (' + label + ') not found in row 1 of tab "' +
        config.tabName + '". Check Settings → Column Headers.'
      );
    }
    return col;
  }

  return {
    colKey:      find('headerJiraKey',      'JIRA Key'),
    colStatus:   find('headerStatus',       'Status'),
    colStart:    find('headerStartDate',    'Start Date'),
    colEnd:      find('headerEndDate',      'Target End Date'),
    colResolved: find('headerResolvedDate', 'Actual End Date')
  };
}

// Reads all script-managed columns for every row in one range call.
// Returns a map of jiraKey -> { row, currentStatus, currentStart, currentEnd, currentResolved }.
function buildKeyMap(sheet, cols) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return {};

  const minCol  = Math.min(cols.colKey, cols.colStatus, cols.colStart, cols.colEnd, cols.colResolved);
  const maxCol  = Math.max(cols.colKey, cols.colStatus, cols.colStart, cols.colEnd, cols.colResolved);
  const numCols = maxCol - minCol + 1;

  const values = sheet.getRange(2, minCol, lastRow - 1, numCols).getValues();
  const map    = {};

  values.forEach(function(row, i) {
    const key = String(row[cols.colKey - minCol] || '').trim();
    if (!key) return;

    map[key] = {
      row:             i + 2,
      currentStatus:   String(row[cols.colStatus   - minCol] || '').trim(),
      currentStart:    String(row[cols.colStart     - minCol] || '').trim(),
      currentEnd:      String(row[cols.colEnd       - minCol] || '').trim(),
      currentResolved: String(row[cols.colResolved  - minCol] || '').trim()
    };
  });

  return map;
}

function writeChangesToSheet(changes, sheet) {
  changes.forEach(function(change) {
    change.fields.forEach(function(fc) {
      sheet.getRange(change.row, fc.col).setValue(fc.value);
    });
  });
}
