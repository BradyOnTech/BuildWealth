// Movement III — The decisions.
// Editorial list of plan decisions with an inline append form.

import { html, raw, esc } from '../../lib/dom.js';
import { roman, fmtRelative } from '../../lib/format.js';

export function renderDecisions(plan, state) {
  const decisions = (plan.decisions || []).slice().reverse();

  return html`
    <section>
      <header class="section-head">
        <span class="section-eyebrow">Movement III</span>
        <h2 class="section-title">The decisions.</h2>
        <p class="section-lede">A trail of what was changed and why — useful when calibration revisits results.</p>
      </header>
      ${decisions.length ? renderList(decisions) : renderEmpty()}
      ${renderAppendArea(state)}
    </section>
  `;
}

function renderList(decisions) {
  return html`
    <ol class="decision-list">
      ${decisions.slice(0, 12).map((d, i) => renderRow(d, i + 1))}
    </ol>
  `;
}

function renderRow(decision, index) {
  const rawStatus = String(decision.status || 'proposed').toLowerCase();
  const tier = canonicalStatus(rawStatus);
  const created = decision.created_at ? fmtRelative(decision.created_at) : '';
  const dateLabel = decision.created_at
    ? new Date(decision.created_at).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
    : '';

  return html`
    <li class="decision-row">
      <span class="decision-numeral">${roman(index)}.</span>
      <div>
        <div class="decision-tag">
          ${dateLabel ? html`<span>${dateLabel.toUpperCase()}</span>` : ''}
          <span class="status ${tier}">
            <span class="dot"></span>${rawStatus}
          </span>
          ${created ? html`<span class="marginalia" style="font-family:var(--serif);font-style:italic;text-transform:none;letter-spacing:0;">${created}</span>` : ''}
        </div>
        <p class="decision-summary">${esc(decision.summary || '')}</p>
        ${decision.rationale ? html`<p class="decision-rationale">${esc(decision.rationale)}</p>` : ''}
      </div>
    </li>
  `;
}

// Map free-form status strings to one of three editorial buckets so the
// dot colour stays consistent regardless of the verb the writer reached for.
function canonicalStatus(s) {
  if (s === 'accepted' || s === 'approved' || s === 'applied' || s === 'done')   return 'accepted';
  if (s === 'rejected' || s === 'declined' || s === 'cancelled' || s === 'abandoned') return 'rejected';
  return 'proposed';
}

function renderEmpty() {
  return html`
    <div class="empty-block">
      <span class="glyph">¶</span>
      <p>No decisions logged yet.</p>
    </div>
  `;
}

function renderAppendArea(state) {
  if (!state.appendOpen) {
    return html`
      <div class="entry-actions" style="margin-top: var(--s-4);">
        <button class="action-link" data-decision-action="open-append">
          Append a decision <span class="arrow">›</span>
        </button>
      </div>
    `;
  }

  return html`
    <div class="append-form" data-form="append-decision">
      <p class="inline-form-title">Log a decision.</p>
      <div class="inline-form-row">
        <label class="inline-label" for="decision-summary">Summary</label>
        <input id="decision-summary" name="summary" type="text" placeholder="What changed, briefly." />
      </div>
      <div class="inline-form-row">
        <label class="inline-label" for="decision-rationale">Rationale (optional)</label>
        <textarea id="decision-rationale" name="rationale" placeholder="Why now? What were you weighing?"></textarea>
      </div>
      <div class="inline-form-row">
        <label class="inline-label" for="decision-status">Status</label>
        <select id="decision-status" name="status">
          <option value="accepted">accepted</option>
          <option value="proposed" selected>proposed</option>
          <option value="rejected">rejected</option>
        </select>
      </div>
      ${state.appendError ? html`<p class="inline-warning">${esc(state.appendError)}</p>` : ''}
      <div class="append-form-actions">
        <button class="btn btn-primary" data-decision-action="submit-append" ${state.appendBusy ? 'disabled' : ''}>
          ${state.appendBusy ? 'Saving…' : 'Save'}
        </button>
        <button class="btn btn-ghost" data-decision-action="cancel-append" ${state.appendBusy ? 'disabled' : ''}>Cancel</button>
      </div>
    </div>
  `;
}
