// Loading-state placeholder. Every view paints the same shimmering
// `.skeleton` block (styles/states.css) while data loads; only the
// dimensions differ, so they're parameters here instead of per-view copies.

import { html } from './dom.js';

export function skeleton(height, { width, marginTop } = {}) {
  const style = `height: ${height};`
    + (width ? ` width: ${width};` : '')
    + (marginTop ? ` margin-top: ${marginTop};` : '');
  return html`<div class="skeleton" style="${style}">.</div>`;
}
