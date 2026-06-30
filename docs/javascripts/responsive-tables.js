// Wrap wide content tables in a horizontal scroll container.
//
// Reports have tables up to 8 columns with long text cells. Left unwrapped,
// they overflow the page on phones and tablets (forcing the whole page to
// scroll sideways). Wrapping each table in a `.md-table-scroll` div confines
// the overflow to that container: it scrolls only when the table is wider than
// the viewport, so desktop tables still render full-width with no scrollbar.
//
// PASSIVE-safe: no scroll/touch handlers, no preventDefault — DOM wrapping only.
(function () {
  function wrapTables() {
    // Material content tables carry no class; skip ones already wrapped.
    const tables = document.querySelectorAll('.md-typeset table:not([class])');
    tables.forEach(table => {
      const parent = table.parentNode;
      if (!parent) return;
      if (parent.classList && parent.classList.contains('md-table-scroll')) return;
      const wrap = document.createElement('div');
      wrap.className = 'md-table-scroll';
      parent.insertBefore(wrap, table);
      wrap.appendChild(table);
    });
  }

  // Material's instant navigation (navigation.instant) swaps page content
  // without a full reload; document$ emits on every page view. Fall back to
  // DOMContentLoaded when instant nav isn't active.
  if (window.document$ && typeof window.document$.subscribe === 'function') {
    window.document$.subscribe(wrapTables);
  } else if (document.readyState !== 'loading') {
    wrapTables();
  } else {
    document.addEventListener('DOMContentLoaded', wrapTables);
  }
})();
