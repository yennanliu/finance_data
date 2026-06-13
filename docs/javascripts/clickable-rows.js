// Make table rows clickable by navigating to the first link in the row.
// Uses event delegation: one listener on document, not one per row.
//
// NOTE: This file is PASSIVE-safe — it never calls preventDefault(), so it
// does not block scrolling. Do NOT add scroll-blocking (passive:false) touch
// handlers here. Pull-to-refresh prevention is handled in CSS via
// `overscroll-behavior` (see stylesheets/extra.css), which is performant and
// does not janky-up mobile scrolling. A previous passive:false touchmove
// handler here ran JS synchronously on every scroll frame and was the cause
// of severe scroll lag on mobile.
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
    // Use link.click() instead of window.location.href so MkDocs Material's
    // instant navigation (SPA router) handles the transition — avoids a full
    // hard page reload (which appears as an "auto refresh" on iOS Safari).
    link.click();
  }
});
