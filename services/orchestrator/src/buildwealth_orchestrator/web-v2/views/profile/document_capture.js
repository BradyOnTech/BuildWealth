// Profile · "From a document" capture card.
// Photograph a paystub, W-2, mortgage statement, or insurance declaration and
// the extract vision model proposes profile entries. The user reviews each
// section, unticks what they don't want, and applies — nothing is saved
// without that explicit step.
//
// Wiring is self-contained: one document-level delegated listener scoped to
// this card's container, so the card works wherever the overview renders it
// and survives full view re-renders without touching views/profile.js.

import { api } from '../../lib/api.js';
import { html, raw, esc } from '../../lib/dom.js';
import { fmtUsd } from '../../lib/format.js';

const SECTION_LABELS = {
  income_items: 'Income',
  expense_items: 'Expenses',
  debt_items: 'Debt',
  tax_profile: 'Tax profile',
};

const DOC_LABELS = {
  paystub: 'Paystub',
  w2: 'W-2',
  mortgage_statement: 'Mortgage statement',
  insurance_declaration: 'Insurance declaration',
  other: 'Document',
};

// Exported for tests: drive the card through its phases without a DOM.
export const captureState = {
  phase: 'idle', // idle | extracting | ready | applying | applied | unconfigured | error
  fileName: null,
  result: null,  // { document_type, confidence, suggestions, warnings, review_note }
  applied: null, // { applied_sections, counts, skipped_duplicates }
  error: null,
};

export function renderDocumentCapture() {
  ensureWired();
  return html`
    <article class="profile-card profile-doc-capture" id="profile-doc-capture">
      ${raw(cardBody())}
    </article>
  `;
}

/* ─────────────  Markup  ───────────── */

function cardBody() {
  return html`
    <header class="profile-card-head">
      <h3 class="profile-card-title">From a document</h3>
    </header>
    <p class="profile-line-detail">
      Photograph a paystub, W-2, mortgage statement, or insurance declaration page.
      BuildWealth reads it into suggestions you review — nothing is saved until you apply.
    </p>
    ${raw(phaseBody())}
  `;
}

function phaseBody() {
  const s = captureState;
  if (s.phase === 'extracting') {
    return html`<p class="profile-card-empty">Reading ${esc(s.fileName || 'the document')}…</p>`;
  }
  if (s.phase === 'applying') {
    return html`<p class="profile-card-empty">Applying to your profile…</p>`;
  }
  if (s.phase === 'unconfigured') {
    return html`
      <p class="profile-card-empty">
        ${esc(s.error || 'No AI provider is configured for document reading.')}
        <a class="link-editorial" href="#settings" data-route>Open Settings</a>
      </p>
      ${raw(resetLink('Try another document'))}
    `;
  }
  if (s.phase === 'error') {
    return html`
      <p class="error-banner">${esc(s.error || 'The document could not be read.')}</p>
      ${raw(resetLink('Try again'))}
    `;
  }
  if (s.phase === 'applied') {
    return appliedBody();
  }
  if (s.phase === 'ready') {
    return reviewBody();
  }
  return idleBody();
}

// The <input> stays in the DOM — onExtract reads the live FileList off it, and a
// drop sets .files via DataTransfer — but its native chrome is hidden so this
// stops being the one unstyled control in the product.
function idleBody() {
  return html`
    <div class="profile-doc-controls">
      <label class="profile-dropzone" data-doccap-dropzone>
        <input type="file" accept="image/*" data-doccap-file />
        <strong>Drop a photo, or choose a file</strong>
        <span class="profile-dropzone-file" data-doccap-filename></span>
        <span>JPG or PNG · stays in this workspace until you apply it</span>
        <span class="profile-dropzone-error" data-doccap-droperror role="alert"></span>
      </label>
      <button class="btn btn-primary" data-doccap-action="extract" disabled>Extract</button>
    </div>
  `;
}

function reviewBody() {
  const result = captureState.result || {};
  const suggestions = result.suggestions || {};
  const sections = Object.keys(SECTION_LABELS).filter(key => hasContent(suggestions[key]));
  const docLabel = DOC_LABELS[result.document_type] || 'Document';

  const header = html`
    <p class="profile-line-detail">
      Read as <strong>${esc(docLabel)}</strong> · confidence ${esc(result.confidence || 'low')}.
      ${esc(result.review_note || 'Check every number against the document before applying.')}
    </p>
  `;

  if (!sections.length) {
    return html`
      ${raw(header)}
      ${raw(warningsList(result.warnings))}
      <p class="profile-card-empty">Nothing usable was read from this document — nothing to apply.</p>
      ${raw(resetLink('Try another photo'))}
    `;
  }

  const sectionCards = sections.map(key => sectionBlock(key, suggestions[key])).join('');
  return html`
    ${raw(header)}
    ${raw(warningsList(result.warnings))}
    ${suggestions.notes_hint ? html`<p class="profile-line-detail">${esc(suggestions.notes_hint)}</p>` : ''}
    <ul class="profile-line-list profile-doc-review">${raw(sectionCards)}</ul>
    <div class="profile-doc-controls">
      <button class="btn btn-primary" data-doccap-action="apply">Apply selected</button>
      <button class="btn btn-quiet" data-doccap-action="reset">Start over</button>
    </div>
  `;
}

function sectionBlock(key, value) {
  const rows = key === 'tax_profile' ? taxRows(value) : itemRows(key, value);
  return html`
    <li class="profile-line profile-doc-section">
      <label class="profile-doc-include">
        <input type="checkbox" checked data-doccap-include="${esc(key)}" />
        <span class="profile-line-label">${esc(SECTION_LABELS[key])}</span>
      </label>
      <ul class="profile-doc-items">${raw(rows)}</ul>
    </li>
  `;
}

function itemRows(key, items) {
  return (Array.isArray(items) ? items : []).map(item => {
    const amount = key === 'debt_items'
      ? `${fmtUsd(item.balance_usd)} balance${item.interest_rate != null ? ` · ${(item.interest_rate * 100).toFixed(2)}%` : ''}${item.minimum_payment_usd != null ? ` · ${fmtUsd(item.minimum_payment_usd)}/mo min` : ''}`
      : `${fmtUsd(item.monthly_amount_usd)}/mo`;
    return html`
      <li class="profile-doc-item">
        <span class="profile-line-value">${esc(item.label || 'Item')}</span>
        <span class="profile-line-detail">${esc(amount)}</span>
      </li>
    `;
  }).join('');
}

function taxRows(tax) {
  const entries = Object.entries(tax && typeof tax === 'object' ? tax : {});
  return entries.map(([field, value]) => {
    const label = field.replace(/_/g, ' ');
    const shown = /rate$/.test(field) && Number.isFinite(Number(value))
      ? `${(Number(value) * 100).toFixed(2)}%`
      : String(value);
    return html`
      <li class="profile-doc-item">
        <span class="profile-line-value">${esc(label)}</span>
        <span class="profile-line-detail">${esc(shown)}</span>
      </li>
    `;
  }).join('');
}

function appliedBody() {
  const applied = captureState.applied || {};
  const counts = applied.counts || {};
  const parts = (applied.applied_sections || [])
    .map(section => `${counts[section] || 0} ${SECTION_LABELS[section] ? SECTION_LABELS[section].toLowerCase() : section}`);
  const skipped = Number(applied.skipped_duplicates || 0);
  return html`
    <p class="profile-card-empty">
      ${parts.length
        ? `Applied to your profile: ${parts.join(', ')}${skipped ? ` (${skipped} duplicate${skipped === 1 ? '' : 's'} skipped)` : ''}. Switch tabs or reload Profile to see the new entries.`
        : `Nothing new to apply${skipped ? ` — ${skipped} duplicate${skipped === 1 ? '' : 's'} were already in the profile` : ''}.`}
    </p>
    ${raw(resetLink('Capture another document'))}
  `;
}

function warningsList(warnings) {
  const list = (Array.isArray(warnings) ? warnings : []).filter(Boolean);
  if (!list.length) return '';
  const rows = list.map(w => html`<li class="profile-doc-warning">${esc(w)}</li>`).join('');
  return html`<ul class="profile-doc-warnings">${raw(rows)}</ul>`;
}

function resetLink(label) {
  return html`<button class="btn btn-quiet" data-doccap-action="reset">${esc(label)}</button>`;
}

function hasContent(value) {
  if (Array.isArray(value)) return value.length > 0;
  if (value && typeof value === 'object') return Object.keys(value).length > 0;
  return false;
}

/* ─────────────  Wiring  ───────────── */

let wired = false;

function ensureWired() {
  if (wired || typeof document === 'undefined') return;
  wired = true;

  // Enabling the button in place (no innerHTML swap) keeps the file the user
  // just picked inside the input element.
  document.addEventListener('change', (e) => {
    const input = e.target?.closest?.('[data-doccap-file]');
    if (!input || !container()?.contains(input)) return;
    const picked = Boolean(input.files && input.files.length);
    const button = container()?.querySelector('[data-doccap-action="extract"]');
    if (button) button.disabled = !picked;
    // Hiding the native control means the chosen filename must be echoed back,
    // or there is no confirmation that anything was picked.
    const name = container()?.querySelector('[data-doccap-filename]');
    if (name) name.textContent = picked ? input.files[0].name : '';
  });

  // Drop writes the file straight onto the input, then re-fires change so the
  // single enable/echo path above stays the only one.
  for (const type of ['dragenter', 'dragover', 'dragleave', 'drop']) {
    document.addEventListener(type, (e) => {
      const zone = e.target?.closest?.('[data-doccap-dropzone]');
      if (!zone || !container()?.contains(zone)) return;
      e.preventDefault();
      if (type === 'dragleave') {
        // dragleave also fires crossing onto the zone's own children, which
        // flickers the highlight. Only a leave that exits the zone counts.
        if (!zone.contains(e.relatedTarget)) zone.classList.remove('dragging');
        return;
      }
      if (type !== 'drop') { zone.classList.add('dragging'); return; }
      zone.classList.remove('dragging');
      const input = zone.querySelector('[data-doccap-file]');
      const file = e.dataTransfer?.files?.[0];
      if (!input) return;
      // accept="image/*" only filters the picker; a drop bypasses it entirely,
      // so a dropped PDF would otherwise go straight to extraction.
      if (!file || !String(file.type || '').startsWith('image/')) {
        setDropError(zone, file ? 'That is not an image. Photograph or screenshot the document instead.' : '');
        return;
      }
      setDropError(zone, '');
      const bag = new DataTransfer();
      bag.items.add(file);
      input.files = bag.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });
  }

  document.addEventListener('click', (e) => {
    const el = e.target?.closest?.('[data-doccap-action]');
    if (!el || !container()?.contains(el)) return;
    e.preventDefault();
    const action = el.getAttribute('data-doccap-action');
    if (action === 'extract') onExtract();
    else if (action === 'apply') onApply();
    else if (action === 'reset') onReset();
  });
}

function setDropError(zone, message) {
  const slot = zone.querySelector('[data-doccap-droperror]');
  if (slot) slot.textContent = message;
}

function container() {
  return document.getElementById('profile-doc-capture');
}

function rerender() {
  const card = typeof document !== 'undefined' ? container() : null;
  if (card) card.innerHTML = String(cardBody());
}

async function onExtract() {
  const input = container()?.querySelector('[data-doccap-file]');
  const file = input?.files?.[0];
  if (!file) return;
  captureState.fileName = file.name;
  captureState.phase = 'extracting';
  captureState.error = null;
  captureState.applied = null;
  rerender();
  try {
    const formData = new FormData();
    formData.append('file', file);
    const result = await api.profileDocumentVision(formData);
    if (result?.status === 'ready') {
      captureState.phase = 'ready';
      captureState.result = result;
    } else if (result?.status === 'unconfigured') {
      captureState.phase = 'unconfigured';
      captureState.error = result?.detail || null;
    } else {
      captureState.phase = 'error';
      captureState.error = result?.detail || 'The document could not be read.';
    }
  } catch (err) {
    captureState.phase = 'error';
    captureState.error = err?.message || 'The document could not be read.';
  }
  rerender();
}

async function onApply() {
  const suggestions = captureState.result?.suggestions || {};
  const patch = {};
  for (const box of container()?.querySelectorAll('[data-doccap-include]') || []) {
    const section = box.getAttribute('data-doccap-include');
    if (box.checked && suggestions[section]) patch[section] = suggestions[section];
  }
  if (!Object.keys(patch).length) return;
  captureState.phase = 'applying';
  rerender();
  try {
    captureState.applied = await api.applyProfileDocumentVision(patch);
    captureState.phase = 'applied';
  } catch (err) {
    captureState.phase = 'error';
    captureState.error = err?.message || 'Could not apply the suggestions.';
  }
  rerender();
}

function onReset() {
  captureState.phase = 'idle';
  captureState.fileName = null;
  captureState.result = null;
  captureState.applied = null;
  captureState.error = null;
  rerender();
}
