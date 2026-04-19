// Make table rows clickable by navigating to the first link in the row.
// Uses event delegation: one listener on document, not one per row.
document.addEventListener('click', function(e) {
  // Walk up from the click target to find a <tr>
  var target = e.target;
  while (target && target.tagName !== 'TR') {
    target = target.parentElement;
  }
  if (!target) return;

  // Only act on rows inside .md-typeset table bodies
  var tbody = target.parentElement;
  if (!tbody || tbody.tagName !== 'TBODY') return;
  var table = tbody.closest('.md-typeset table');
  if (!table) return;

  // Don't double-navigate when clicking a link directly
  if (e.target.tagName === 'A' || e.target.closest('a')) return;

  var link = target.querySelector('a');
  if (link) {
    window.location.href = link.href;
  }
});
