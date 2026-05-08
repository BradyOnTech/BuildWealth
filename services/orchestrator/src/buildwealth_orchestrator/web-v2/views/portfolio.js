// PORTFOLIO — three movements.
//   I.   The standing       — total value + performance
//   II.  The composition    — allocation strata + top holdings
//   III. The watch          — risk alerts or all-clear
// Footer — Look closer (links to classic surfaces for actions not yet rebuilt).

import { api } from '../lib/api.js';
import { state } from '../lib/state.js';
import { html, raw, $, esc, setView } from '../lib/dom.js';
import { renderStanding } from './portfolio/standing.js';
import { renderComposition } from './portfolio/composition.js';
import { renderWatch } from './portfolio/watch.js';

const MONEY_FMT = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

export const meta = {
  id: 'portfolio',
  label: 'Portfolio',
  numeral: 'IV',
  group: 'primary',
};

export function template() {
  return html`
    <section class="page" id="portfolio-page">
      <div class="portfolio-shell" id="portfolio-shell">
        ${raw(skeletonHero())}
        ${raw(skeletonSection('II', 'The composition'))}
        ${raw(skeletonSection('III', 'The watch'))}
      </div>
    </section>
  `;
}

export async function init(params = {}) {
  const root = $('#portfolio-shell');
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
        <label class="fit-field">
          <span>Proposed account</span>
          <input name="proposed_account_id" type="text" autocomplete="off" placeholder="Optional account id">
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
  const proposedAccountId = String(formData.get('proposed_account_id') || '').trim();
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
    if (proposedAccountId) body.proposed_account_id = proposedAccountId;
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
  const accountLocation = impact.account_location || {};
  const proposedAccount = formatProposedAccount(impact.proposed_account);
  const policyCap = formatPolicyCap(impact);
  const policyGuardrails = formatPolicyGuardrails(impact.investment_policy);
  const sectorPolicy = formatSectorPolicy(impact);
  const contributionGuidance = formatContributionGuidance(impact.contribution_guidance);
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
        ${policyCap ? html`
          <div>
            <dt>Policy cap</dt>
            <dd>${policyCap}</dd>
          </div>
        ` : ''}
        ${policyGuardrails ? html`
          <div>
            <dt>Policy</dt>
            <dd>${policyGuardrails}</dd>
          </div>
        ` : ''}
        ${sectorPolicy ? html`
          <div>
            <dt>Sector policy</dt>
            <dd>${sectorPolicy}</dd>
          </div>
        ` : ''}
        <div>
          <dt>Account location</dt>
          <dd>${formatTaxTreatments(accountLocation)}</dd>
        </div>
        ${proposedAccount ? html`
          <div>
            <dt>Proposed account</dt>
            <dd>${proposedAccount}</dd>
          </div>
        ` : ''}
        ${contributionGuidance ? html`
          <div>
            <dt>Contribution fit</dt>
            <dd>${contributionGuidance}</dd>
          </div>
        ` : ''}
      </dl>
      ${raw(renderAccountLocation(accountLocation))}
      ${raw(renderEvidenceAction(result.symbol, evidence))}
      ${raw(renderBullets('Reasons', result.fit_reasons))}
      ${raw(renderBullets('Risks', result.fit_risks))}
      ${raw(renderBullets('Needs', result.blocking_gaps))}
    </article>
  `;
}

function renderEvidenceAction(symbol, evidence = {}) {
  const packetId = String(evidence.packet_id || evidence.research_evidence_packet_id || '').trim();
  if (!symbol || !packetId) return '';
  const href = `#research?symbol=${encodeURIComponent(String(symbol).toUpperCase())}&packet=${encodeURIComponent(packetId)}`;
  return html`
    <div class="entry-actions">
      <a class="action-link muted" href="${href}">Open evidence <span class="arrow">→</span></a>
    </div>
  `;
}

function renderAccountLocation(accountLocation = {}) {
  const accounts = Array.isArray(accountLocation.accounts)
    ? accountLocation.accounts.filter(Boolean).slice(0, 3)
    : [];
  const warnings = Array.isArray(accountLocation.warnings)
    ? accountLocation.warnings.filter(Boolean).slice(0, 2)
    : [];
  if (!accounts.length && !warnings.length) return '';

  return html`
    <div class="fit-list">
      <h3>Account location</h3>
      <ul>
        ${accounts.map((account) => html`<li>${formatAccountLocationRow(account)}</li>`)}
        ${warnings.map((warning) => html`<li>${warning}</li>`)}
      </ul>
    </div>
  `;
}

function formatAccountLocationRow(account = {}) {
  const parts = [
    account.account_name || account.account_id || 'Unknown account',
    labelize(account.tax_treatment || account.account_type || 'unknown'),
    account.unrealized_gain_loss_usd != null
      ? `${MONEY_FMT.format(Number(account.unrealized_gain_loss_usd) || 0)} gain/loss`
      : '',
    account.lot_term_mix ? `${labelize(account.lot_term_mix)} lots` : '',
  ].filter(Boolean);
  return parts.join(' · ');
}

function formatTaxTreatments(accountLocation = {}) {
  const treatments = Array.isArray(accountLocation.tax_treatments)
    ? accountLocation.tax_treatments.filter(Boolean)
    : [];
  if (treatments.length) return treatments.map(labelize).join(', ');
  if (accountLocation.tax_lot_coverage === 'missing') return 'Tax lots missing';
  return 'Not available';
}

function formatProposedAccount(account = {}) {
  if (!account || typeof account !== 'object') return '';
  const preferred = Array.isArray(account.policy_preferred_treatments)
    ? account.policy_preferred_treatments.filter(Boolean)
    : [];
  const parts = [
    account.account_name || account.account_id || '',
    labelize(account.tax_treatment || account.account_type || ''),
    preferred.length ? `prefers ${preferred.map(labelize).join(', ')}` : '',
  ].filter(Boolean);
  return parts.join(' · ');
}

function formatContributionGuidance(guidance = {}) {
  if (!guidance || typeof guidance !== 'object') return '';
  const reasons = Array.isArray(guidance.review_reasons)
    ? guidance.review_reasons.filter(Boolean)
    : [];
  const parts = [
    guidance.status ? labelize(guidance.status) : '',
    guidance.tax_treatment ? labelize(guidance.tax_treatment) : '',
    guidance.recommended_review ? labelize(guidance.recommended_review) : '',
    reasons[0] || '',
  ].filter(Boolean);
  return parts.join(' · ');
}

function formatPolicyCap(portfolioImpact = {}) {
  const cap = Number(portfolioImpact.single_holding_max_pct);
  if (!Number.isFinite(cap)) return '';
  const source = portfolioImpact.single_holding_policy_source === 'profile.investment_policy'
    ? 'Personal policy'
    : 'Portfolio policy';
  return `${cap.toLocaleString('en-US', { maximumFractionDigits: 1 })}% · ${source}`;
}

function formatPolicyGuardrails(policy = {}) {
  if (!policy || typeof policy !== 'object') return '';
  const restrictedSymbols = Array.isArray(policy.restricted_symbols) ? policy.restricted_symbols.filter(Boolean) : [];
  const restrictedSectors = Array.isArray(policy.restricted_sectors) ? policy.restricted_sectors.filter(Boolean) : [];
  const parts = [
    policy.minimum_research_confidence ? `Research ${labelize(policy.minimum_research_confidence)}` : '',
    policy.minimum_cash_runway_months != null ? `Cash floor ${Number(policy.minimum_cash_runway_months).toLocaleString('en-US', { maximumFractionDigits: 1 })} mo` : '',
    formatAssetClassCaps(policy.max_asset_class_exposure_pct, 'Asset cap'),
    policy.simplicity_preference ? `Simplicity ${labelize(policy.simplicity_preference)}` : '',
    policy.tax_sensitivity ? `Tax ${labelize(policy.tax_sensitivity)}` : '',
    policy.risk_tolerance ? `Risk ${labelize(policy.risk_tolerance)}` : '',
    policy.max_sector_exposure_pct != null ? `Sector cap ${Number(policy.max_sector_exposure_pct).toLocaleString('en-US', { maximumFractionDigits: 1 })}%` : '',
    restrictedSymbols.length ? `Avoid ${restrictedSymbols.slice(0, 2).join(', ')}` : '',
    restrictedSectors.length ? `Avoid ${restrictedSectors.slice(0, 2).map(labelize).join(', ')}` : '',
  ].filter(Boolean);
  return parts.join(' · ');
}

function formatAssetClassCaps(caps, label) {
  if (!caps || typeof caps !== 'object' || Array.isArray(caps)) return '';
  const rows = Object.entries(caps)
    .filter(([, value]) => Number.isFinite(Number(value)))
    .slice(0, 2)
    .map(([key, value]) => `${labelize(key)} ${Number(value).toLocaleString('en-US', { maximumFractionDigits: 1 })}%`);
  return rows.length ? `${label} ${rows.join(', ')}` : '';
}

function formatSectorPolicy(portfolioImpact = {}) {
  const sector = String(portfolioImpact.candidate_sector || '').trim();
  const weight = Number(portfolioImpact.sector_weight_after_trade_pct);
  const cap = Number(portfolioImpact.sector_max_pct);
  if (!sector || !Number.isFinite(weight) || !Number.isFinite(cap)) return '';
  return `${sector} ${weight.toLocaleString('en-US', { maximumFractionDigits: 1 })}% · cap ${cap.toLocaleString('en-US', { maximumFractionDigits: 1 })}%`;
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
  // Movement V — Maintenance. Lower-frequency operations that don't belong
  // in the daily portfolio narrative but should be discoverable from here.
  // Each card deep-links to its current classic surface; v2 will absorb
  // these one at a time.
  const sections = [
    { label: 'Accounts',         href: '/classic#portfolio',         hint: 'Brokerage and account-level metadata' },
    { label: 'Transactions',     href: '/classic#portfolio',         hint: 'Buy/sell/dividend history' },
    { label: 'Custom assets',    href: '/classic#portfolio',         hint: 'Real estate, vehicles, collectibles' },
    { label: 'Manual prices',    href: '/classic#portfolio',         hint: 'Override or backfill quotes' },
    { label: 'FX rates',         href: '/classic#portfolio',         hint: 'Currency conversion rates' },
    { label: 'Cost basis',       href: '/classic#portfolio',         hint: 'Lot-level basis adjustments' },
    { label: 'Risk policy',      href: '#profile?section=investing', hint: 'Single-investment, cash cushion, sectors' },
    { label: 'Lot audit',        href: '/classic#portfolio',         hint: 'Reconcile lots against statements' },
    { label: 'Corporate actions',href: '/classic#portfolio',         hint: 'Splits, mergers, spin-offs' },
  ];
  return html`
    <section>
      <header class="section-head">
        <span class="section-eyebrow">Movement V</span>
        <h2 class="section-title">Maintenance</h2>
        <p class="section-lede">
          Lower-frequency tools that keep the picture honest. Each opens the
          classic surface for now — v2 absorbs them one at a time as the
          input shape stabilises.
        </p>
      </header>
      <div class="portfolio-maintenance-grid">
        ${raw(sections.map(s => `
          <a class="portfolio-maintenance-card"
             href="${esc(s.href)}"
             ${s.href.startsWith('#') ? 'data-route' : ''}>
            <span class="portfolio-maintenance-label">${esc(s.label)}</span>
            <span class="portfolio-maintenance-hint">${esc(s.hint)}</span>
            <span class="portfolio-maintenance-arrow">→</span>
          </a>
        `).join(''))}
      </div>
    </section>
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
