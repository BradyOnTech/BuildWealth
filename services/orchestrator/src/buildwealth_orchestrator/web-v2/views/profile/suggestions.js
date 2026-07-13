// Suggested values — the UI face of the smart-defaults engine.
// Fields that the app can estimate render a labeled suggestion line with a
// one-tap "Use" action; nothing is written until the user saves the form.

import { api } from '../../lib/api.js';
import { html, esc } from '../../lib/dom.js';

let cache = null;

export async function loadProfileSuggestions({ refresh = false } = {}) {
  if (cache && !refresh) return cache;
  try {
    const payload = await api.profileDefaults();
    cache = payload?.suggestions && typeof payload.suggestions === 'object'
      ? payload.suggestions
      : {};
  } catch {
    cache = {};
  }
  return cache;
}

export function invalidateProfileSuggestions() {
  cache = null;
}

export function getSuggestion(suggestions, fieldPath) {
  const entry = suggestions?.[fieldPath];
  return entry && typeof entry === 'object' ? entry : null;
}

/* Render the suggestion line under a field. `target` is the input/select id
   the Use button fills; `format` maps the raw value to the input's unit
   (e.g. decimal rate -> percent). */
export function suggestionLine(suggestions, fieldPath, { target, format } = {}) {
  const entry = getSuggestion(suggestions, fieldPath);
  if (!entry) return '';
  const inputValue = format ? format(entry.value) : entry.value;
  const basisLabel = entry.basis === 'computed' ? 'estimated from your data' : 'typical household';
  return html`
    <span class="suggestion-line">
      <button type="button" class="suggestion-use"
              data-use-suggestion
              data-suggestion-target="${esc(String(target || ''))}"
              data-suggestion-value="${esc(String(inputValue ?? ''))}">
        Use ${esc(String(entry.display || entry.value))}
      </button>
      <span class="suggestion-why">· ${esc(String(entry.explanation || basisLabel))}</span>
    </span>
  `.toString();
}

/* Click handler for [data-use-suggestion] buttons — fills the target control
   and fires input/change so the form's normal save path sees the value. */
export function applySuggestionClick(el, root = document) {
  const targetId = el.getAttribute('data-suggestion-target') || '';
  const value = el.getAttribute('data-suggestion-value') ?? '';
  const control = root.querySelector(`#${CSS.escape(targetId)}`);
  if (!control) return false;
  control.value = value;
  control.dispatchEvent(new Event('input', { bubbles: true }));
  control.dispatchEvent(new Event('change', { bubbles: true }));
  control.focus();
  return true;
}
