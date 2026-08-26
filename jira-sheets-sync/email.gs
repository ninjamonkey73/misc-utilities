const FIELD_LABELS = {
  status:        'Status',
  startDate:     'Start Date',
  targetEndDate: 'Target End Date',
  actualEndDate: 'Actual End Date'
};

function sendDigestEmail(changes, newItems, missingItems, unclassified, config, triggeredBySchedule) {
  unclassified = unclassified || [];
  const hasContent = changes.length > 0 || newItems.length > 0 || missingItems.length > 0 || unclassified.length > 0;
  if (!hasContent) return;

  const recipient = triggeredBySchedule
    ? config.notifyEmails
    : Session.getEffectiveUser().getEmail();

  if (!recipient || !recipient.trim()) return;

  const tz      = Session.getScriptTimeZone();
  const dateStr = Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd');
  const timeStr = Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd HH:mm z');
  const divider = '─'.repeat(60) + '\n';
  const subject = 'JIRA Sync — ' + changes.length + ' status change(s) detected (' + dateStr + ')';
  const sheetUrl = SpreadsheetApp.getActiveSpreadsheet().getUrl();

  let body = '';

  if (changes.length > 0) {
    body += 'STATUS CHANGES (' + changes.length + '):\n' + divider;
    changes.forEach(function(c) {
      body += c.key + '  —  ' + c.summary + '\n';
      c.fields.forEach(function(f) {
        const label   = FIELD_LABELS[f.field] || f.field;
        const prevVal = f.prevValue || '(empty)';
        body += '    ' + label + ': ' + prevVal + ' → ' + f.value + '\n';
      });
    });
    body += '\n';
  }

  if (newItems.length > 0) {
    body += divider;
    body += 'NEW STORIES IN JIRA — please add a row manually (' + newItems.length + '):\n\n';
    newItems.forEach(function(i) {
      body += '  ' + i.key + '  —  ' + i.summary + '\n';
    });
    body += '\n';
  }

  if (missingItems.length > 0) {
    body += divider;
    body += 'ROWS NOT FOUND IN TODAY\'S JIRA RESULTS — verify and remove manually if rejected (' +
            missingItems.length + '):\n\n';
    missingItems.forEach(function(i) {
      body += '  ' + i.key + '  —  Last known status: ' + i.lastStatus + '\n';
    });
    body += '\n';
  }

  if (unclassified.length > 0) {
    body += divider;
    body += 'UNCLASSIFIED ISSUES — no status mapping JQL matched (' + unclassified.length + '):\n';
    body += 'Status column was NOT updated. Check your status mappings in Settings.\n\n';
    unclassified.forEach(function(i) {
      body += '  ' + i.key + '  —  ' + i.summary + '\n';
    });
    body += '\n';
  }

  body += divider;
  body += 'View sheet: ' + sheetUrl + '\n';
  body += 'Run by:     ' + Session.getEffectiveUser().getEmail() + '\n';
  body += 'Time:       ' + timeStr + '\n';

  GmailApp.sendEmail(recipient, subject, body);
}
