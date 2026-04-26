// Sweep — Movement II.
// Run all factories against current state, preview candidates, then create.

import { api } from '../../lib/api.js';
import { html, raw } from '../../lib/dom.js';

const SOURCE_LABELS = {
  portfolio_risk:  'portfolio risk',
  plan_tracking:   'plan tracking',
  cash_liquidity:  'cash & liquidity',
};

export function renderSweep(sweep) {
  return html`
    <section>
      ${raw(sectionHead('II', 'A new sweep.', 'Look at the current state and surface fresh candidates.'))}
      <div class="sweep-card">
        ${raw(renderSweepBody(sweep))}
      </div>
    </section>
  `;
}

function renderSweepBody(sweep) {
  if (sweep.phase === 'idle') {
    return html`
      <div class="entry-actions">
        <button class="action-link" data-sweep="preview" ${sweep.busy ? 'disabled' : ''}>
          Sweep for new suggestions <span class="arrow">›</span>
        </button>
      </div>
    `;
  }
  if (sweep.phase === 'previewing') {
    return html`<p class="marginalia">Looking through the factories…</p>`;
  }
  if (sweep.phase === 'preview-ready') {
    const counts = sweep.preview?.counts || {};
    const total = sweep.preview?.total ?? Object.values(counts).reduce((a, b) => a + b, 0);
    const skipped = sweep.preview?.skipped ?? 0;
    return html`
      ${raw(renderSourceCounts(counts))}
      <p class="marginalia">${total} candidate${total === 1 ? '' : 's'}${skipped ? ` · ${skipped} skipped (already active)` : ''}</p>
      <div class="entry-actions">
        <button class="action-link" data-sweep="create" ${total === 0 ? 'disabled' : ''}>
          Create ${total === 0 ? 'no new suggestions' : `${total} suggestion${total === 1 ? '' : 's'}`} <span class="arrow">›</span>
        </button>
        <button class="action-link muted" data-sweep="reset">
          Cancel <span class="arrow">›</span>
        </button>
      </div>
    `;
  }
  if (sweep.phase === 'creating') {
    return html`<p class="marginalia">Filing the new suggestions…</p>`;
  }
  if (sweep.phase === 'done') {
    const created = sweep.created ?? 0;
    return html`
      <p class="quality-quote">Filed ${created} new suggestion${created === 1 ? '' : 's'}.</p>
      <div class="entry-actions">
        <button class="action-link muted" data-sweep="reset">
          Sweep again <span class="arrow">›</span>
        </button>
      </div>
    `;
  }
  if (sweep.phase === 'error') {
    return html`
      <p class="inline-warning">${sweep.error || 'The sweep could not finish.'}</p>
      <div class="entry-actions">
        <button class="action-link muted" data-sweep="reset">
          Try again <span class="arrow">›</span>
        </button>
      </div>
    `;
  }
  return '';
}

function renderSourceCounts(counts) {
  const entries = Object.entries(counts);
  if (!entries.length) return '';
  return html`
    <dl class="sweep-results">
      ${raw(entries.map(([key, count]) => `
        <div class="sweep-source">
          <dt>${SOURCE_LABELS[key] || key.replace(/_/g, ' ')}</dt>
          <dd>${count}<span class="of"></span></dd>
        </div>
      `).join(''))}
    </dl>
  `;
}

export async function runPreview() {
  const res = await api.sweepPreview();
  return normalizeSweepResponse(res);
}

export async function runCreate() {
  const res = await api.sweepCreate();
  return normalizeSweepResponse(res);
}

function normalizeSweepResponse(res) {
  const factories = res.factories || res.results || res.groups || {};
  const counts = {};
  let createdItems = 0;

  if (factories && typeof factories === 'object' && !Array.isArray(factories)) {
    for (const [key, group] of Object.entries(factories)) {
      const count = group?.generated_count ?? (Array.isArray(group?.candidates) ? group.candidates.length : 0);
      counts[key] = count || 0;
      createdItems += Array.isArray(group?.created) ? group.created.length : 0;
    }
  }

  return {
    counts,
    total:   res.generated_count ?? Object.values(counts).reduce((a, b) => a + b, 0),
    skipped: res.skipped_count ?? 0,
    created: createdItems || res.generated_count || 0,
    raw:     res,
  };
}

function sectionHead(numeral, title, lede) {
  return html`
    <header class="section-head">
      <span class="section-eyebrow">Movement ${numeral}</span>
      <h2 class="section-title">${title}</h2>
      ${lede ? html`<p class="section-lede">${lede}</p>` : ''}
    </header>
  `;
}
