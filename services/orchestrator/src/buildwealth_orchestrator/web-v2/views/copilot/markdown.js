// Markdown rendering for Copilot replies.
// Uses the vendored `marked` parser (MIT-licensed) with editorial defaults.

import { marked } from '../../lib/marked.esm.js';

marked.setOptions({
  gfm: true,           // tables, strikethrough, fenced code
  breaks: false,       // GitHub-style soft breaks off — use proper paragraphs
  pedantic: false,
  smartypants: false,  // we already render with Fraunces oldstyle figures
  headerIds: false,
  mangle: false,
});

// Lightweight sanitiser — removes <script> and javascript: URLs from rendered
// output. Marked already escapes inline HTML, but defence-in-depth is cheap.
const SCRIPT_PATTERN = /<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi;
const ON_ATTR_PATTERN = /\son[a-z]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]*)/gi;
const JS_HREF_PATTERN = /\s(href|src)\s*=\s*("javascript:[^"]*"|'javascript:[^']*')/gi;

export function renderMarkdown(source) {
  if (!source) return '';
  const text = String(source);
  const rendered = marked.parse(text);
  return rendered
    .replace(SCRIPT_PATTERN, '')
    .replace(ON_ATTR_PATTERN, '')
    .replace(JS_HREF_PATTERN, '');
}
