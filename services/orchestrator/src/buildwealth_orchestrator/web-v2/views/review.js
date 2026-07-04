// THE ANNUAL EDITION — the Almanac reviews its year.
// An editorial compilation of the numbers, the decisions, and how they aged.
// Designed to be read, and to be printed (print = save as PDF).

import { api } from '../lib/api.js';
import { html, raw, setView, $, delegate } from '../lib/dom.js';
import { fmtUsd, fmtUsdSigned, splitUsd, fmtDateLong } from '../lib/format.js';
import { compactUsd } from '../lib/chart.js';
import { computeFiProgress, buildDeltaDecomposition } from './today.js';

export const meta = {
  id: 'review',
  label: 'Annual Edition',
  numeral: '·',
  group: 'utility',
};

export function template() {
  return html`
    <section class="page" id="review-page">
      <div class="review-shell" id="review-shell">
        <p class="marginalia">Compiling the edition...</p>
      </div>
    </section>
  `;
}

export async function init() {
  const root = $('#review-shell');
  if (!root) return;

  const [health, analytics, plans] = await Promise.all([
    api.financialHealth().catch(() => null),
    api.portfolioAnalytics({ period: '1y' }).catch(() => null),
    api.plans().catch(() => null),
  ]);
  const planList = Array.isArray(plans?.plans) ? plans.plans : (Array.isArray(plans) ? plans : []);
  const planId = String(planList[0]?.id || '');
  const [plan, savedSims] = await Promise.all([
    planId ? api.plan(planId).catch(() => null) : null,
    planId ? api.planSavedSimulations(planId).catch(() => null) : null,
  ]);

  setView(root, raw(renderReviewDocument({ health, analytics, plan, savedSims, now: new Date() })));
  delegate(root, 'click', '[data-review-action="print"]', () => window.print());
}

// Pure document render — testable without a DOM.
export function renderReviewDocument({ health, analytics, plan, savedSims, now = new Date() } = {}) {
  const year = now.getFullYear();
  return html`
    <article class="review-document">
      ${raw(masthead(year, now))}
      ${raw(theStanding(health, analytics))}
      ${raw(theJourney(health))}
      ${raw(thePortfolioYear(analytics))}
      ${raw(theDecisions(plan, year))}
      ${raw(theExperiments(savedSims))}
      ${raw(closingPage(health))}
    </article>
  `.toString();
}

function masthead(year, now) {
  return html`
    <header class="review-masthead">
      <p class="review-folio">The Wealth Almanac</p>
      <h1 class="review-title">The ${year} Edition</h1>
      <p class="review-dateline">
        Compiled ${fmtDateLong(now)} · trailing twelve months
        <button class="action-link review-print" data-review-action="print">Print / save as PDF <span class="arrow">›</span></button>
      </p>
    </header>
  `;
}

function theStanding(health, analytics) {
  const netWorth = Number(health?.net_worth_usd);
  if (!Number.isFinite(netWorth)) {
    return sectionShell('I', 'The standing', html`<p class="marginalia">Add profile and portfolio data to open the ledger.</p>`);
  }
  const { currency, number } = splitUsd(netWorth);
  const terms = buildDeltaDecomposition(analytics);
  return sectionShell('I', 'The standing', html`
    <h2 class="hero-number review-number"><span class="currency">${currency}</span>${number}</h2>
    ${terms.length ? html`
      <p class="marginalia review-decomposition">
        The year in causes:
        ${raw(terms.map(term => html`
          <span class="${term.value >= 0 ? 'delta-up' : 'delta-down'}"><b class="num-mono">${fmtUsdSigned(term.value)}</b> ${term.label}</span>
        `).join(' · '))}
      </p>
    ` : ''}
  `);
}

function theJourney(health) {
  const fi = computeFiProgress(health);
  const rows = [
    fi ? ['Progress to financial independence', `${fi.progressPct}% of ${compactUsd(fi.targetUsd)}`] : null,
    Number.isFinite(Number(health?.savings_rate_pct)) ? ['Savings rate', `${Number(health.savings_rate_pct).toFixed(1)}%`] : null,
    Number.isFinite(Number(health?.emergency_fund_months)) ? ['Emergency runway', `${Number(health.emergency_fund_months).toFixed(1)} months`] : null,
    Number.isFinite(Number(health?.debt_to_income_ratio_pct)) ? ['Debt to income', `${Number(health.debt_to_income_ratio_pct).toFixed(1)}%`] : null,
  ].filter(Boolean);
  if (!rows.length) return '';
  return sectionShell('II', 'The journey', html`
    <dl class="scenario-change-list review-journey">
      ${raw(rows.map(([label, value]) => html`
        <div><dt>${label}</dt><dd>${value}</dd></div>
      `).join(''))}
    </dl>
  `);
}

function thePortfolioYear(analytics) {
  const performance = objectValue(analytics?.performance);
  const attribution = objectValue(analytics?.attribution);
  const benchmark = objectValue(analytics?.benchmark);
  if (!Object.keys(performance).length) return '';

  const metrics = [
    ['Time-weighted return', pctOrNull(performance.twr_annualized_return_pct ?? performance.twr_return_pct)],
    ['Money-weighted (XIRR)', pctOrNull(performance.xirr_annualized_return_pct)],
    ['Income received', usdOrNull(performance.income_return_usd)],
    ['Fees paid', usdOrNull(performance.fees_paid_usd)],
  ].filter(([, value]) => value != null);
  const benchmarkRows = (Array.isArray(benchmark.rows) ? benchmark.rows : []).slice(0, 2);
  const contributors = (Array.isArray(attribution.contributors) ? attribution.contributors : []).slice(0, 3);
  const detractors = (Array.isArray(attribution.detractors) ? attribution.detractors : []).slice(0, 3);

  return sectionShell('III', "The portfolio's year", html`
    ${metrics.length ? html`
      <dl class="scenario-change-list">
        ${raw(metrics.map(([label, value]) => html`<div><dt>${label}</dt><dd>${value}</dd></div>`).join(''))}
      </dl>
    ` : ''}
    ${benchmarkRows.length ? html`
      <p class="marginalia">
        Against the benchmark:
        ${raw(benchmarkRows.map(row => html`
          <span>${clean(row.symbol)} ${pctOrNull(row.alpha_pct) ?? '—'} alpha</span>
        `).join(' · '))}
      </p>
    ` : ''}
    ${contributors.length || detractors.length ? html`
      <div class="review-attribution">
        ${raw(attributionColumn('Carried the year', contributors, 'up'))}
        ${raw(attributionColumn('Cost the year', detractors, 'down'))}
      </div>
    ` : ''}
  `);
}

function attributionColumn(title, rows, direction) {
  if (!rows.length) return '';
  return html`
    <div class="review-attribution-col">
      <h4>${title}</h4>
      ${raw(rows.map(row => html`
        <p>
          <strong>${clean(row.symbol)}</strong>
          <span class="${direction === 'down' ? 'delta-down' : 'delta-up'}">${fmtUsdSigned(numberOr(row.total_return, 0))}</span>
        </p>
      `).join(''))}
    </div>
  `;
}

function theDecisions(plan, year) {
  const decisions = (Array.isArray(plan?.decisions) ? plan.decisions : [])
    .filter(item => item && typeof item === 'object')
    .filter(item => {
      const created = new Date(item.created_at || 0);
      return !Number.isNaN(created.getTime()) && created.getFullYear() >= year - 1;
    })
    .slice(-8)
    .reverse();
  const measured = decisions.filter(item => item.outcome_captured).length;
  const body = decisions.length
    ? html`
      <p class="marginalia">${decisions.length} recorded · ${measured} with outcomes measured. A decision without a measured outcome is a bet still open.</p>
      ${raw(decisions.map(item => html`
        <div class="review-decision">
          <p class="review-decision-title"><strong>${clean(item.label) || 'Decision'}</strong> <span class="marginalia">${fmtDateLong(item.created_at)}</span></p>
          ${clean(item.rationale) ? html`<p class="review-decision-note">${clean(item.rationale)}</p>` : ''}
          ${clean(item.expected_outcome) ? html`<p class="review-decision-note">Expected: ${clean(item.expected_outcome)}</p>` : ''}
          ${clean(item.realized_outcome) ? html`<p class="review-decision-note">Realized: ${clean(item.realized_outcome)}</p>` : ''}
        </div>
      `).join(''))}
    `
    : html`<p class="marginalia">No decisions were recorded this year. The Almanac can only review what it is told — record the next one in Plan.</p>`;
  return sectionShell('IV', 'The decisions', body);
}

function theExperiments(savedSims) {
  const sims = (Array.isArray(savedSims?.simulations) ? savedSims.simulations : []).slice(0, 5);
  if (!sims.length) return '';
  return sectionShell('V', 'The experiments', html`
    <p class="marginalia">${sims.length} saved simulation${sims.length === 1 ? '' : 's'} kept for the record.</p>
    ${raw(sims.map(item => html`
      <p class="review-decision-note"><strong>${clean(item.title) || 'Simulation'}</strong> · ${fmtDateLong(item.created_at)}</p>
    `).join(''))}
  `);
}

function closingPage(health) {
  const highlights = (Array.isArray(health?.highlights) ? health.highlights : []).slice(0, 5);
  return sectionShell('VI', 'The closing page', html`
    ${highlights.length ? html`
      <ul class="affordability-highlights">
        ${raw(highlights.map(item => html`<li>${item}</li>`).join(''))}
      </ul>
    ` : ''}
    <p class="review-closing">
      Questions worth carrying into next year: what would make this plan fail
      that nothing above measures? Which decision aged worst, and what did it
      share with the ones that aged well?
      <a class="link-editorial" href="#plan?section=branches">Test one in a what-if</a> ·
      <a class="link-editorial" href="#copilot">Take one to Copilot</a>
    </p>
  `);
}

function sectionShell(numeral, title, body) {
  return html`
    <section class="review-section">
      <header class="section-head compact">
        <span class="section-eyebrow">${numeral} · ${title}</span>
      </header>
      ${raw(String(body))}
    </section>
  `.toString();
}

function pctOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(1)}%` : null;
}

function usdOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) && number !== 0 ? fmtUsd(number) : null;
}

function numberOr(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function objectValue(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function clean(value) {
  return String(value ?? '').trim();
}
