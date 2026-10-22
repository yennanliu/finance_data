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

  // Tag figure columns so report.css can right-align them, and mark cells that
  // open with an explicit sign. Text inspection only — nothing is computed.
  // A column counts as figures when at least 60% of its non-empty body cells
  // read as a number with an optional sign, currency, unit or trailing note.
  const NUM = /^[~≈≥≤<>]?\s*[+\-−]?\s*(?:US\$|NT\$|[$¥€£])?\s*\d[\d,]*(?:\.\d+)?\s*(?:%|x|X|倍|B|M|K|bp|bps|pp|億|萬|元)?(?:\s*[(（][^)）]{0,24}[)）])?$/;
  const SIGNED = /^[+\-−]\s*(?:US\$|NT\$|[$¥€£])?\s*\d/;

  function cellText(cell) {
    // Drop emoji status dots and arrows the reports append to figures.
    return cell.textContent.replace(/[\u{1F300}-\u{1FAFF}\u2190-\u21FF\u2B00-\u2BFF\uFE0F]/gu, '').trim();
  }

  function tagFigures() {
    document.querySelectorAll('.md-typeset table:not([class])').forEach(table => {
      if (table.dataset.figures) return;
      table.dataset.figures = '1';
      const rows = Array.from(table.tBodies[0] ? table.tBodies[0].rows : []);
      if (!rows.length) return;
      const cols = Math.max(...rows.map(r => r.cells.length));
      for (let c = 1; c < cols; c++) {           // column 0 names the row
        let filled = 0, nums = 0;
        rows.forEach(r => {
          const cell = r.cells[c];
          const t = cell ? cellText(cell) : '';
          if (!t || t === '—' || t === '-' || t === 'N/A') return;
          filled++;
          if (NUM.test(t)) nums++;
        });
        if (!filled || nums / filled < 0.6) continue;
        const head = table.tHead && table.tHead.rows[0] && table.tHead.rows[0].cells[c];
        if (head) head.classList.add('is-num');
        rows.forEach(r => {
          const cell = r.cells[c];
          if (!cell) return;
          cell.classList.add('is-num');
          const t = cellText(cell);
          if (NUM.test(t) && SIGNED.test(t)) cell.classList.add(/^[+]/.test(t) ? 'is-pos' : 'is-neg');
        });
      }
    });
  }

  function run() { wrapTables(); tagFigures(); }

  // Material's instant navigation (navigation.instant) swaps page content
  // without a full reload; document$ emits on every page view. Fall back to
  // DOMContentLoaded when instant nav isn't active.
  if (window.document$ && typeof window.document$.subscribe === 'function') {
    window.document$.subscribe(run);
  } else if (document.readyState !== 'loading') {
    run();
  } else {
    document.addEventListener('DOMContentLoaded', run);
  }
})();
