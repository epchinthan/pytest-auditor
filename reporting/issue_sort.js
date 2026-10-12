/* Shared ordering for live and standalone reports. Severity rank starts with errors. */
function compareIssues(a, b, key = 'severity', direction = 'asc') {
  const text = (x, y) => String(x ?? '').localeCompare(String(y ?? ''), 'en', {numeric:true, sensitivity:'base'});
  const severity = issue => ({error:0, warning:1, info:2}[issue.level] ?? 3);
  const file = () => text(a.file, b.file) || Number(a.line || 0) - Number(b.line || 0);
  let comparison;
  if (key === 'code') comparison = text(a.code, b.code) || severity(a) - severity(b) || file();
  else if (key === 'file') comparison = file() || severity(a) - severity(b) || text(a.code, b.code);
  else comparison = severity(a) - severity(b) || text(a.code, b.code) || file();
  return direction === 'desc' ? -comparison : comparison;
}
if (typeof module !== 'undefined') module.exports = {compareIssues};
