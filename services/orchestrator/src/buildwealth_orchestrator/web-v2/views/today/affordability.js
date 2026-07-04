// Price a decision — the affordability question box.
// The one question people actually bring to a money app: "can I afford this?"
// Backend does the math against the saved profile; this surface asks and answers.

import { api } from '../../lib/api.js';
import { html, raw, esc, $, delegate } from '../../lib/dom.js';
import { fmtUsd, fmtUsdSigned } from '../../lib/format.js';

const ui = {
  draft: { mode: 'one_time' },
  busy: false,
  result: null,
  error: null,
};

const VERDICTS = {
  affordable: { title: 'Affordable.', badge: 'Fits your plan', tone: 'high' },
  stretch: { title: 'A stretch.', badge: 'Thin margins', tone: 'medium' },
  not_affordable: { title: 'Not affordable right now.', badge: 'Would strain the plan', tone: 'low' },
  insufficient_data: { title: 'Not enough profile data.', badge: 'Add income first', tone: 'low' },
};

export function buildAffordabilityPayload(draft = {}) {
  const payload = { description: clean(draft.description) || 'Unnamed decision' };
  const amount = toNumber(draft.amount);
  if (amount == null || amount <= 0) return null;
  if (clean(draft.mode) === 'monthly') {
    payload.monthly_amount_usd = amount;
    return payload;
  }
  payload.purchase_price_usd = amount;
  const rate = toNumber(draft.loan_rate_pct);
  const term = toNumber(draft.loan_term_years);
  const down = toNumber(draft.down_payment_pct);
  if (rate != null && rate > 0) payload.loan_rate_pct = rate;
  if (term != null && term > 0) payload.loan_term_years = Math.round(term);
  if (down != null && down >= 0) payload.down_payment_pct = down;
  return payload;
}

export function renderAffordabilitySection(state = ui) {
  const oneTime = clean(state.draft.mode) !== 'monthly';
  return html`
    <section class="today-affordability" id="today-affordability">
      <header class="section-head compact">
        <span class="section-eyebrow">IV · Price a decision</span>
        <h2 class="section-title">Can we afford it?</h2>
        <p class="section-lede">Priced against your saved income, expenses, and debts. Nothing is changed or committed.</p>
      </header>

      ${state.error ? html`<p class="error-banner">${state.error}</p>` : ''}

      <div class="scenario-grid" data-form="today-affordability">
        <label class="scenario-field">
          <span class="assumption-label">What is it?</span>
          <input data-affordability-field="description" type="text" placeholder="A newer car, the kitchen, tuition..." value="${clean(state.draft.description)}" />
          <span class="assumption-current">Short label for the decision</span>
        </label>
        <label class="scenario-field">
          <span class="assumption-label">Kind of cost</span>
          <select data-affordability-field="mode">
            <option value="one_time" ${oneTime ? 'selected' : ''}>One-time purchase</option>
            <option value="monthly" ${oneTime ? '' : 'selected'}>Monthly commitment</option>
          </select>
          <span class="assumption-current">${oneTime ? 'Loan fields optional below' : 'Recurring, e.g. a lease or subscription'}</span>
        </label>
        <label class="scenario-field">
          <span class="assumption-label">${oneTime ? 'Price' : 'Monthly amount'}</span>
          <input data-affordability-field="amount" type="number" step="100" inputmode="decimal" value="${clean(state.draft.amount)}" />
          <span class="assumption-current">USD</span>
        </label>
        ${oneTime ? html`
          <label class="scenario-field">
            <span class="assumption-label">Loan rate</span>
            <input data-affordability-field="loan_rate_pct" type="number" step="0.1" inputmode="decimal" value="${clean(state.draft.loan_rate_pct)}" />
            <span class="assumption-current">% APR · blank for cash</span>
          </label>
          <label class="scenario-field">
            <span class="assumption-label">Loan term</span>
            <input data-affordability-field="loan_term_years" type="number" step="1" inputmode="numeric" value="${clean(state.draft.loan_term_years)}" />
            <span class="assumption-current">Years</span>
          </label>
          <label class="scenario-field">
            <span class="assumption-label">Down payment</span>
            <input data-affordability-field="down_payment_pct" type="number" step="1" inputmode="decimal" value="${clean(state.draft.down_payment_pct)}" />
            <span class="assumption-current">% of price</span>
          </label>
        ` : ''}
      </div>

      <div class="scenario-actions">
        <button class="btn btn-primary" data-affordability-action="run" ${state.busy ? 'disabled' : ''}>
          ${state.busy ? 'Pricing...' : 'Price it'}
        </button>
        <span class="marginalia">Answers use today's profile, not live simulations.</span>
      </div>

      ${state.result ? raw(renderVerdict(state.result)) : ''}
    </section>
  `.toString();
}

function renderVerdict(result = {}) {
  const verdict = VERDICTS[clean(result.assessment)] || VERDICTS.insufficient_data;
  const highlights = (Array.isArray(result.highlights) ? result.highlights : []).slice(0, 4);
  const loanNote = result.is_loan_estimate && result.estimated_monthly_payment_usd != null
    ? ` (${fmtUsd(result.estimated_monthly_payment_usd)}/mo loan estimate)`
    : '';
  return html`
    <article class="simulation-explainer" data-affordability-verdict="${clean(result.assessment)}">
      <header>
        <div>
          <span class="story-block-eyebrow">${clean(result.description) || 'The verdict'}</span>
          <h4>${verdict.title}</h4>
        </div>
        <span class="simulation-confidence ${verdict.tone}">${verdict.badge}</span>
      </header>
      <p>${clean(result.assessment_detail)}${loanNote}</p>
      <dl class="scenario-change-list">
        <div>
          <dt>Monthly cost</dt>
          <dd>${fmtUsd(result.proposed_monthly_usd)}</dd>
        </div>
        <div>
          <dt>Monthly surplus</dt>
          <dd>${fmtUsd(result.current_monthly_surplus_usd)} -> ${fmtUsd(result.new_monthly_surplus_usd)}</dd>
        </div>
        <div>
          <dt>Savings rate</dt>
          <dd>${pct(result.current_savings_rate_pct)} -> ${pct(result.new_savings_rate_pct)}</dd>
        </div>
        <div>
          <dt>Debt-to-income</dt>
          <dd>${pct(result.current_dti_pct)} -> ${pct(result.new_dti_pct)}</dd>
        </div>
        ${Number(result.annual_savings_reduction_usd) > 0 ? html`
          <div>
            <dt>Yearly savings impact</dt>
            <dd>${fmtUsdSigned(-Number(result.annual_savings_reduction_usd))}</dd>
          </div>
        ` : ''}
      </dl>
      ${highlights.length ? html`
        <ul class="affordability-highlights">
          ${raw(highlights.map(item => html`<li>${item}</li>`).join(''))}
        </ul>
      ` : ''}
      ${result.plan_impact_detail ? html`<p class="marginalia">${result.plan_impact_detail}</p>` : ''}
      <div class="scenario-handoff">
        <a class="link-editorial" href="#copilot?intent=affordability">Talk it through in Copilot</a>
        <a class="link-editorial" href="#plan?section=scenarios">Run it as a full simulation</a>
      </div>
    </article>
  `;
}

// One delegated binding on the Today shell; survives section re-renders.
export function bindAffordabilitySection(rootEl) {
  delegate(rootEl, 'input', '[data-affordability-field]', (_, el) => stage(el, { rerender: false }));
  delegate(rootEl, 'change', '[data-affordability-field]', (_, el) => stage(el, { rerender: el.dataset.affordabilityField === 'mode' }));
  delegate(rootEl, 'click', '[data-affordability-action="run"]', () => run());
}

function stage(el, { rerender = false } = {}) {
  const field = clean(el.dataset.affordabilityField);
  if (!field) return;
  ui.draft = { ...ui.draft, [field]: el.value };
  ui.error = null;
  if (rerender) rerenderSection();
}

async function run() {
  if (ui.busy) return;
  const payload = buildAffordabilityPayload(ui.draft);
  if (!payload) {
    ui.error = 'Enter an amount above zero to price the decision.';
    rerenderSection();
    return;
  }
  ui.busy = true;
  ui.error = null;
  rerenderSection();
  try {
    ui.result = await api.affordability(payload);
  } catch (err) {
    ui.result = null;
    ui.error = err.message;
  } finally {
    ui.busy = false;
    rerenderSection();
  }
}

function rerenderSection() {
  const section = $('#today-affordability');
  if (!section) return;
  section.outerHTML = renderAffordabilitySection(ui);
}

function pct(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(1)}%` : '—';
}

function toNumber(value) {
  const text = clean(value);
  if (!text) return null;
  const number = Number(text);
  return Number.isFinite(number) ? number : null;
}

function clean(value) {
  return String(value ?? '').trim();
}
