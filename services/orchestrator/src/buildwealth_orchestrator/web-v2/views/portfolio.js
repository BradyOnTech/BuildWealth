// PORTFOLIO — three movements.
//   I.   The standing       — total value + performance
//   II.  The composition    — allocation strata + top holdings
//   III. The watch          — risk alerts or all-clear
// Footer — Look closer (links to classic surfaces for actions not yet rebuilt).

import { api } from '../lib/api.js';
import { state } from '../lib/state.js';
import { html, raw, $, setView } from '../lib/dom.js';
import { renderStanding } from './portfolio/standing.js';
import { renderComposition } from './portfolio/composition.js';
import { renderWatch } from './portfolio/watch.js';

export const meta = {
  id: 'portfolio',
  label: 'Portfolio',
  numeral: 'II',
  group: 'daily',
};

export function template() {
  return html`
    <section class="page" id="portfolio-page">
      ${raw(skeletonHero())}
      ${raw(skeletonSection('II', 'The composition'))}
      ${raw(skeletonSection('III', 'The watch'))}
    </section>
  `;
}

export async function init(params = {}) {
  const root = $('#portfolio-page');
  if (!root) return;
  let data = null;
  try {
    data = await api.holdings();
    state.portfolio = data;
  } catch (err) {
    setView(root, html`
      <p class="hero-eyebrow">Portfolio</p>
      <p class="error-banner">${err.message}</p>
    `);
    return;
  }

  setView(root, html`
    ${raw(renderStanding(data))}
    ${raw(renderComposition(data))}
    ${raw(renderWatch(data))}
    ${raw(renderFitReview(null, { initialSymbol: params.fit || '' }))}
    ${raw(renderLookCloser())}
  `);
  bindFitReview(root);
  if (params.fit) {
    const fitSection = root.querySelector('.fit-review');
    if (fitSection) fitSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    runFitReview(root);
  }
}

export function renderFitReview(result = null, { loading = false, error = '', initialSymbol = '' } = {}) {
  const symbolValue = result?.symbol || String(initialSymbol || '').trim().toUpperCase();
  const title = symbolValue
    ? `Fit review: ${symbolValue}`
    : 'Fit review';
  return html`
    <section class="fit-review" aria-labelledby="portfolio-fit-title">
      <header class="section-head">
        <span class="section-eyebrow">Movement IV</span>
        <h2 class="section-title" id="portfolio-fit-title">${title}</h2>
      </header>
      <form class="fit-review-form" data-fit-review-form>
        <label class="fit-field">
          <span>Candidate</span>
          <input name="symbol" type="text" autocomplete="off" placeholder="VTI" maxlength="12" value="${symbolValue}" required>
        </label>
        <label class="fit-field">
          <span>Amount</span>
          <input name="amount_usd" type="number" inputmode="decimal" min="1" step="100" placeholder="Optional">
        </label>
        <button class="fit-review-button" type="submit" ${loading ? 'disabled' : ''}>${loading ? 'Reviewing' : 'Review fit'}</button>
      </form>
      <div class="fit-review-result" data-fit-review-result>
        ${error ? html`<p class="error-banner">${error}</p>` : raw(renderFitResult(result))}
      </div>
    </section>
  `;
}

function bindFitReview(root) {
  const form = root.querySelector('[data-fit-review-form]');
  if (!form) return;
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    runFitReview(root);
  });
}

async function runFitReview(root) {
  const form = root.querySelector('[data-fit-review-form]');
  const resultEl = root.querySelector('[data-fit-review-result]');
  if (!form || !resultEl) return;
  const formData = new FormData(form);
  const symbol = String(formData.get('symbol') || '').trim().toUpperCase();
  const amountRaw = String(formData.get('amount_usd') || '').trim();
  if (!symbol) return;

  const button = form.querySelector('button[type="submit"]');
  if (button) {
    button.disabled = true;
    button.textContent = 'Reviewing';
  }
  setView(resultEl, html`<p class="fit-empty">Checking portfolio, plan horizon, profile readiness, and research evidence.</p>`);
  try {
    const body = { symbol };
    if (amountRaw) body.amount_usd = Number(amountRaw);
    const result = await api.portfolioFit(body);
    setView(resultEl, renderFitResult(result));
  } catch (err) {
    setView(resultEl, html`<p class="error-banner">${err.message || 'Could not review fit.'}</p>`);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = 'Review fit';
    }
  }
}

export function renderFitResult(result) {
  if (!result) {
    return html`
      <p class="fit-empty">Ask whether a candidate belongs in this portfolio before opening a deeper Copilot discussion.</p>
    `;
  }
  const status = labelize(result.fit_status);
  const next = labelize(result.recommended_next_step);
  const evidence = result.evidence || {};
  const plan = result.plan_impact || {};
  const impact = result.portfolio_impact || {};
  return html`
    <article class="fit-result fit-${result.fit_status}">
      <div class="fit-result-head">
        <span class="fit-status">${status}</span>
        <span class="fit-score">${Math.round(Number(result.fit_score || 0))}/100</span>
      </div>
      <dl class="fit-meta">
        <div>
          <dt>Next</dt>
          <dd>${next}</dd>
        </div>
        <div>
          <dt>Plan horizon</dt>
          <dd>${plan.time_horizon ? `${labelize(plan.time_horizon)}${plan.years ? ` · ${plan.years}y` : ''}` : 'Not available'}</dd>
        </div>
        <div>
          <dt>Research</dt>
          <dd>${evidence.freshness_status || 'Unavailable'}${evidence.confidence ? ` · ${evidence.confidence}` : ''}</dd>
        </div>
        <div>
          <dt>Position</dt>
          <dd>${impact.existing_position ? `${Number(impact.current_weight_pct || 0).toFixed(1)}% held` : 'Not held'}</dd>
        </div>
      </dl>
      ${raw(renderBullets('Reasons', result.fit_reasons))}
      ${raw(renderBullets('Risks', result.fit_risks))}
      ${raw(renderBullets('Needs', result.blocking_gaps))}
    </article>
  `;
}

function renderBullets(label, items = []) {
  const visible = Array.isArray(items) ? items.filter(Boolean).slice(0, 4) : [];
  if (!visible.length) return '';
  return html`
    <div class="fit-list">
      <h3>${label}</h3>
      <ul>${visible.map((item) => html`<li>${item}</li>`)}</ul>
    </div>
  `;
}

function labelize(value) {
  return String(value || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (ch) => ch.toUpperCase()) || 'Unknown';
}

function renderLookCloser() {
  return html`
    <footer class="look-closer">
      <span class="section-eyebrow">Look closer</span>
      <div class="look-closer-row">
        <a class="link-editorial" href="/#portfolio">Full holdings table</a>
        <a class="link-editorial" href="/#portfolio">Record a transaction</a>
        <a class="link-editorial" href="/#portfolio">Backfill history</a>
        <a class="link-editorial" href="/#portfolio">Watchlist</a>
        <a class="link-editorial" href="/#portfolio">Risk thresholds</a>
      </div>
      <p class="look-closer-note">Each opens the classic surface — these views haven't been re-set in the new vocabulary yet.</p>
    </footer>
  `;
}

function skeletonHero() {
  return html`
    <section class="hero-stack">
      <span class="hero-eyebrow skeleton" style="width: 280px;">.</span>
      <h1 class="hero-number skeleton" style="width: 60%; height: var(--t-hero);">.</h1>
      <p class="hero-marginalia skeleton" style="width: 480px;">.</p>
    </section>
  `;
}

function skeletonSection(numeral, title) {
  return html`
    <section>
      <header class="section-head">
        <span class="section-eyebrow">Movement ${numeral}</span>
        <h2 class="section-title">${title}</h2>
      </header>
      <div class="skeleton" style="height: 120px;">.</div>
    </section>
  `;
}
