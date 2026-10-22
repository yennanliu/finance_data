"""MkDocs hook: minify every rendered page with minify-html.

Replaces mkdocs-minify-plugin's `minify_html`, which ran htmlmin — a
pure-Python HTML parser — over all ~9.9k pages and was a third of the nightly
build. minify-html is a Rust extension: on a 500-page sample of the built site
it was ~8x faster and its output ~3% smaller.

Only whitespace and comments are touched. Inline <script>/<style> bodies are
left as written (minify_js / minify_css off): the hand-written scripts in
docs/overrides are not worth the risk of a JS minifier for a few KB. <pre>
content — code blocks and the Mermaid sources the client-side renderer reads —
is preserved verbatim; that was checked across 600 built pages and ~10k <pre>
blocks before switching.

Skipping minification is not an option: it still takes ~300 MB off a site that
is already over GitHub Pages' 1 GB soft limit, and every byte is uploaded on
every deploy.
"""
from __future__ import annotations

import minify_html


def on_post_page(output: str, page, config) -> str:
    return minify_html.minify(
        output,
        minify_js=False,
        minify_css=False,
        keep_closing_tags=True,
        keep_html_and_head_opening_tags=True,
    )
