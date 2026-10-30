/*
 * math_harness.mjs — assertions over docs/javascripts/math.js
 * ===========================================================
 * math.js turns the `<span class="arithmatex">\( … \)</span>` that
 * build_docs.display_math() + arithmatex produce into KaTeX. Worth verifying:
 * KaTeX is fetched only on a page with an equation, each span is rendered
 * from its TeX without the \( \) delimiters, and a `\displaystyle` span (one
 * that had a line of its own) gets its own row.
 *
 * KaTeX itself is a stub: loading it from the CDN is the browser's job.
 *
 * Run directly:   node tests/js/math_harness.mjs
 * Run via pytest: tests/test_math_js.py
 */

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCRIPT = path.join(HERE, "..", "..", "docs", "javascripts", "math.js");

let passed = 0;
const failures = [];
function check(name, cond, detail) {
  if (cond) { passed++; return; }
  failures.push(detail ? `${name}\n      ${detail}` : name);
}

function span(tex) {
  const classes = new Set(["arithmatex"]);
  return {
    textContent: tex,
    classList: { add: (c) => classes.add(c), contains: (c) => classes.has(c) },
  };
}

/** Run math.js over `spans`; resolve with what it appended and rendered. */
async function run(spans) {
  const appended = [];
  const rendered = [];
  const katex = { render: (tex, el, opts) => rendered.push({ tex, el, opts }) };
  const window = {};
  const document = {
    readyState: "complete",
    querySelectorAll: (sel) => (sel === ".arithmatex" ? spans : []),
    createElement: (tag) => ({ tagName: tag }),
    head: {
      appendChild: (node) => {
        appended.push(node);
        // The CDN script "loads": KaTeX appears, then onload fires.
        if (node.tagName === "script") setTimeout(() => { window.katex = katex; node.onload(); }, 0);
      },
    },
  };
  vm.runInNewContext(fs.readFileSync(SCRIPT, "utf8"), { window, document, Promise, setTimeout });
  await new Promise((r) => setTimeout(r, 10));
  return { appended, rendered };
}

// ── a page with no equations fetches nothing ────────────────────────────────
{
  const { appended, rendered } = await run([]);
  check("no equation, no KaTeX fetch", appended.length === 0, `appended ${appended.length}`);
  check("no equation, nothing rendered", rendered.length === 0);
}

// ── RKLB 2026-10-28: an own-line §8.8 chain and an inline DCF step ──────────
{
  const own = span("\\(\\displaystyle \\frac{\\$58.90 - \\$58.60}{\\$58.90} = \\frac{+\\$0.30}{\\$58.90}\\)");
  const inline = span("\\(\\$890.0\\text{M} \\times (1 + 38.0\\%) = \\mathbf{\\$1,228.2M}\\)");
  const { appended, rendered } = await run([own, inline]);
  const css = appended.find((n) => n.tagName === "link");
  const js = appended.find((n) => n.tagName === "script");
  check("KaTeX stylesheet pinned", css && /katex@0\.16\.11\/dist\/katex\.min\.css$/.test(css.href), css && css.href);
  check("KaTeX script pinned", js && /katex@0\.16\.11\/dist\/katex\.min\.js$/.test(js.src), js && js.src);
  check("both spans rendered", rendered.length === 2, `rendered ${rendered.length}`);
  check("delimiters stripped (own line)",
        rendered[0] && rendered[0].tex === "\\displaystyle \\frac{\\$58.90 - \\$58.60}{\\$58.90} = \\frac{+\\$0.30}{\\$58.90}",
        rendered[0] && rendered[0].tex);
  check("delimiters stripped (inline)",
        rendered[1] && rendered[1].tex === "\\$890.0\\text{M} \\times (1 + 38.0\\%) = \\mathbf{\\$1,228.2M}",
        rendered[1] && rendered[1].tex);
  check("errors never throw", rendered.every((r) => r.opts.throwOnError === false));
  check("own-line span gets its own row", own.classList.contains("arithmatex--line"));
  check("inline span stays inline", !inline.classList.contains("arithmatex--line"));
}

console.log(`${passed} passed, ${failures.length} failed`);
for (const f of failures) console.log(`  ✗ ${f}`);
process.exit(failures.length ? 1 : 0);
