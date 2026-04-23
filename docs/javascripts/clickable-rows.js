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
    // Use link.click() instead of window.location.href so MkDocs Material's
    // instant navigation (SPA router) handles the transition — avoids a full
    // hard page reload (which appears as an "auto refresh" on iOS Safari).
    link.click();
  }
});

// ── iOS pull-to-refresh prevention ──────────────────────────────────────────
// CSS `overscroll-behavior-y: none` is unreliable on iOS Safari (<16) and
// some Android WebViews. This JS approach works cross-platform:
// when the page is already scrolled to the top and the user pulls DOWN,
// preventDefault() cancels the native refresh gesture.
(function () {
  var touchStartY = 0;

  document.addEventListener('touchstart', function (e) {
    touchStartY = e.touches[0].clientY;
  }, { passive: true });

  document.addEventListener('touchmove', function (e) {
    var scrollTop =
      document.documentElement.scrollTop ||
      document.body.scrollTop ||
      0;
    var touchY = e.touches[0].clientY;

    // Only block when already at the top AND pulling downward
    if (scrollTop === 0 && touchY > touchStartY) {
      e.preventDefault();
    }
  }, { passive: false }); // passive: false required to allow preventDefault()
})();
