// PORTFOLIO — three movements.
//   I.   The standing       — total value + performance
//   II.  The composition    — allocation strata + top holdings
//   III. Performance        — returns, benchmark comparison, attribution
//   IV.  The watch          — risk alerts or all-clear
// Footer — Look closer (native maintenance records and audit follow-through).

import { api } from '../lib/api.js';
import { state } from '../lib/state.js';
import { html, raw, $, esc, setView } from '../lib/dom.js';
import { renderStanding } from './portfolio/standing.js';
import { renderComposition } from './portfolio/composition.js';
import { renderAnalytics } from './portfolio/analytics.js';
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
  const maintenanceSection = normalizeMaintenanceSection(params.section || '');
  let maintenance = null;
  let analytics = null;
  try {
    const [holdingsData, analyticsData, maintenanceData] = await Promise.all([
      api.holdings(),
      api.portfolioAnalytics({ limit: 180, topN: 5 }).catch((err) => ({
        status: 'unavailable',
        warnings: [err?.message || 'Performance analytics are unavailable.'],
      })),
      maintenanceSection ? loadMaintenanceSection(maintenanceSection, params) : Promise.resolve(null),
    ]);
    data = holdingsData;
    analytics = analyticsData;
    maintenance = maintenanceSection === 'risk-policy' && maintenanceData
      ? { ...maintenanceData, riskAlerts: holdingsData?.risk_alerts || null }
      : maintenanceData;
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
    ${raw(renderAnalytics(analytics))}
    ${raw(renderWatch(data))}
    ${raw(renderFitReview(null, { initialSymbol: params.fit || '' }))}
    ${raw(renderLookCloser(maintenanceSection, maintenance))}
  `);
  bindFitReview(root);
  bindMaintenanceTools(root);
  if (params.fit) {
    const fitSection = root.querySelector('.fit-review');
    if (fitSection) fitSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    runFitReview(root);
  }
  if (maintenanceSection) {
    const maintenanceEl = root.querySelector('[data-portfolio-maintenance-detail]');
    if (maintenanceEl) maintenanceEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
      <span class="section-eyebrow">Movement V</span>
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

export function renderLookCloser(activeSection = '', maintenance = null) {
  const sections = [
    { id: 'audit', label: 'Portfolio Audit', hint: 'Import checks, review items, and follow-through' },
    { id: 'accounts', label: 'Accounts', hint: 'Brokerage and account-level metadata' },
    { id: 'transactions', label: 'Transactions', hint: 'Buy/sell/dividend history' },
    { id: 'assets', label: 'Investments & Assets', hint: 'Searchable registry, metadata, and review status' },
    { id: 'prices', label: 'Manual prices', hint: 'Override or backfill quotes' },
    { id: 'fx', label: 'FX rates', hint: 'Currency conversion rates' },
    { id: 'cost-basis', label: 'Cost basis', hint: 'Lot-level basis adjustments' },
    { id: 'risk-policy', label: 'Guardrails', hint: 'Plain limits for concentration, accounts, sectors, and spread' },
  ];
  return html`
    <section>
      <header class="section-head">
        <span class="section-eyebrow">Movement VI</span>
        <h2 class="section-title">Maintenance</h2>
        <p class="section-lede">
          Lower-frequency tools that keep the picture honest. Import reports,
          account review, and source evidence resolve here inside BuildWealth.
        </p>
      </header>
      <div class="portfolio-maintenance-grid">
        ${raw(sections.map(s => `
          <a class="portfolio-maintenance-card"
             href="${esc(s.href || `#portfolio?section=${s.id}`)}"
             data-route>
            <span class="portfolio-maintenance-label">${esc(s.label)}</span>
            <span class="portfolio-maintenance-hint">${esc(s.hint)}</span>
            <span class="portfolio-maintenance-arrow">→</span>
          </a>
        `).join(''))}
      </div>
      ${raw(renderMaintenanceDetail(activeSection, maintenance))}
    </section>
  `;
}

function normalizeMaintenanceSection(section) {
  const value = String(section || '').trim().toLowerCase();
  const aliases = {
    account: 'accounts',
    accounts: 'accounts',
    audit: 'audit',
    reconciliation: 'audit',
    review: 'audit',
    transaction: 'transactions',
    transactions: 'transactions',
    asset: 'assets',
    assets: 'assets',
    'custom-assets': 'assets',
    prices: 'prices',
    price: 'prices',
    'manual-prices': 'prices',
    fx: 'fx',
    'fx-rates': 'fx',
    'cost-basis': 'cost-basis',
    cost_basis: 'cost-basis',
    guardrails: 'risk-policy',
    guardrail: 'risk-policy',
    risk: 'risk-policy',
    'risk-policy': 'risk-policy',
    risk_policy: 'risk-policy',
    allocation: 'risk-policy',
  };
  return aliases[value] || '';
}

async function loadMaintenanceSection(section, params = {}) {
  try {
    if (section === 'audit') return { section, payload: await api.portfolioAudit(25) };
    if (section === 'accounts') return { section, rows: await api.portfolioAccounts() };
    if (section === 'transactions') return { section, rows: await api.portfolioTransactions(100) };
    if (section === 'assets') {
      const payload = await api.portfolioAssetSearch({ q: params.q || '', limit: 200 });
      return { section, rows: payload.items || [], payload };
    }
    if (section === 'prices') return { section, payload: await api.portfolioManualPrices() };
    if (section === 'fx') return { section, payload: await api.portfolioFxRates() };
    if (section === 'cost-basis') return { section, payload: await api.portfolioCostBasisMethods() };
    if (section === 'risk-policy') return { section, payload: await api.portfolioRiskPolicy() };
  } catch (err) {
    return { section, error: err?.message || 'Could not load this portfolio section.' };
  }
  return null;
}

function renderMaintenanceDetail(section, maintenance) {
  if (!section) return '';
  if (maintenance?.error) {
    return html`
      <article class="portfolio-maintenance-detail" data-portfolio-maintenance-detail>
        <p class="error-banner">${maintenance.error}</p>
      </article>
    `;
  }

  const title = section === 'assets'
    ? 'Investments & Assets'
    : (section === 'audit' ? 'Portfolio Audit' : (section === 'risk-policy' ? 'Portfolio Guardrails' : labelize(section)));
  const rows = maintenanceRows(section, maintenance);
  return html`
    <article class="portfolio-maintenance-detail" data-portfolio-maintenance-detail>
      <header class="section-head compact">
        <span class="section-eyebrow">Portfolio maintenance</span>
        <h3 class="section-title">${title}</h3>
        <p class="section-lede">${maintenanceCopy(section)}</p>
      </header>
      ${section === 'audit' ? raw(renderPortfolioAudit(maintenance?.payload || {})) : ''}
      ${section === 'assets' ? raw(renderAssetRegistryTools(maintenance)) : ''}
      ${section === 'risk-policy' ? raw(renderRiskGuardrails(maintenance)) : ''}
      ${section === 'audit' || section === 'risk-policy'
        ? ''
        : (rows.length ? raw(renderMaintenanceRows(section, rows)) : html`<p class="fit-empty">Nothing recorded here yet.</p>`)}
    </article>
  `;
}

const RISK_GUARDRAIL_FIELDS = [
  {
    key: 'single_holding_max_pct',
    label: 'One investment max',
    unit: '%',
    min: 0,
    max: 100,
    step: '0.5',
    help: 'Warn when one holding takes up too much of the portfolio.',
  },
  {
    key: 'top3_holdings_max_pct',
    label: 'Top 3 investments max',
    unit: '%',
    min: 0,
    max: 100,
    step: '0.5',
    help: 'Warn when the three biggest holdings carry too much of the portfolio.',
  },
  {
    key: 'account_max_pct',
    label: 'One account max',
    unit: '%',
    min: 0,
    max: 100,
    step: '0.5',
    help: 'Warn when too much value sits in one account.',
  },
  {
    key: 'asset_class_max_pct',
    label: 'One investment type max',
    unit: '%',
    min: 0,
    max: 100,
    step: '0.5',
    help: 'Warn when one broad type, like stocks or bonds, dominates.',
  },
  {
    key: 'sector_max_pct',
    label: 'One sector max',
    unit: '%',
    min: 0,
    max: 100,
    step: '0.5',
    help: 'Warn when one business sector gets too large.',
  },
  {
    key: 'region_max_pct',
    label: 'One region max',
    unit: '%',
    min: 0,
    max: 100,
    step: '0.5',
    help: 'Warn when one country or region carries too much exposure.',
  },
  {
    key: 'hhi_max',
    label: 'Concentration score max',
    unit: '',
    min: 0.01,
    max: 1,
    step: '0.01',
    help: 'A smaller score means the portfolio is more spread out.',
  },
  {
    key: 'effective_positions_min',
    label: 'Minimum spread',
    unit: '',
    min: 1,
    max: 100,
    step: '1',
    help: 'The minimum number of meaningfully different positions.',
  },
];

function renderRiskGuardrails(maintenance = {}) {
  const policy = maintenance?.payload || {};
  const thresholds = policy.thresholds || {};
  const alerts = maintenance?.riskAlerts || {};
  const alertItems = Array.isArray(alerts.alerts) ? alerts.alerts : [];
  return html`
    <div class="portfolio-guardrails">
      <div class="portfolio-guardrails-explainer">
        <div>
          <h4>How BuildWealth reads this</h4>
          <p>
            Watch means close to a limit. Low, medium, and high mean how far a current holding,
            account, sector, region, or concentration score has moved past the limit.
          </p>
        </div>
        <dl>
          <div><dt>High</dt><dd>Far past the limit and worth reviewing first.</dd></div>
          <div><dt>Medium</dt><dd>Past the limit enough to plan a fix.</dd></div>
          <div><dt>Low</dt><dd>Slightly past the limit or close enough to watch.</dd></div>
        </dl>
      </div>
      <form class="portfolio-guardrails-form" data-risk-policy-form>
        <div class="portfolio-guardrails-grid">
          ${raw(RISK_GUARDRAIL_FIELDS.map(field => renderRiskGuardrailField(field, thresholds[field.key])).join(''))}
        </div>
        <div class="portfolio-guardrails-actions">
          <button class="fit-review-button" type="submit">Save guardrails</button>
          <p class="portfolio-guardrails-status" data-risk-policy-status>
            Saving refreshes the current guardrail check.
          </p>
        </div>
      </form>
      ${raw(renderRiskAlertSummary(alertItems, alerts))}
    </div>
  `;
}

function renderRiskGuardrailField(field, value) {
  const displayValue = Number.isFinite(Number(value)) ? Number(value) : '';
  return html`
    <label class="portfolio-guardrail-field">
      <span class="portfolio-guardrail-label">
        ${field.label}
        ${field.unit ? raw(`<em>${esc(field.unit)}</em>`) : ''}
      </span>
      <input
        name="${field.key}"
        type="number"
        min="${String(field.min)}"
        max="${String(field.max)}"
        step="${field.step}"
        value="${String(displayValue)}"
        required
      >
      <span class="portfolio-guardrail-help">${field.help}</span>
    </label>
  `;
}

function renderRiskAlertSummary(alerts = [], meta = {}) {
  const visible = alerts.slice(0, 6);
  const status = String(meta.status || 'ok');
  const breachCount = Number(meta.breach_count || 0);
  const watchCount = Number(meta.watch_count || 0);
  return html`
    <div class="portfolio-guardrails-alerts">
      <div class="portfolio-guardrails-alert-head">
        <div>
          <h4>Current guardrail check</h4>
          <p>${breachCount} over limit · ${watchCount} close to a limit · ${labelize(status)}</p>
        </div>
        <span class="portfolio-guardrails-pill ${classToken(status)}">${labelize(status)}</span>
      </div>
      ${visible.length ? html`
        <div class="portfolio-guardrails-alert-list">
          ${raw(visible.map(renderRiskAlertItem).join(''))}
        </div>
      ` : html`<p class="fit-empty">No active guardrail alerts. The current portfolio is inside these limits.</p>`}
    </div>
  `;
}

function renderRiskAlertItem(alert = {}) {
  const detail = formatRiskAlertDetail(alert);
  const severity = String(alert.severity || 'low');
  const state = String(alert.state || 'watch');
  return html`
    <article class="portfolio-guardrail-alert ${classToken(severity)}">
      <div>
        <span>${labelize(state)} · ${labelize(severity)}</span>
        <h5>${alert.label || 'Guardrail alert'}</h5>
        <p>${detail || alert.message || ''}</p>
      </div>
      <p>${alert.recommendation || 'Review this before making the next portfolio change.'}</p>
    </article>
  `;
}

function classToken(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9_-]+/g, '');
}

function formatRiskAlertDetail(alert = {}) {
  const observed = formatRiskMetric(alert, alert.observed);
  const threshold = formatRiskMetric(alert, alert.threshold);
  if (!observed || !threshold) return alert.message || '';
  const direction = alert.direction === 'min' ? 'minimum' : 'limit';
  return `${observed} now · ${threshold} ${direction}`;
}

function formatRiskMetric(alert = {}, value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '';
  if (alert.unit === 'pct') return `${number.toLocaleString('en-US', { maximumFractionDigits: 1 })}%`;
  if (alert.unit === 'ratio') return number.toLocaleString('en-US', { maximumFractionDigits: 3 });
  return number.toLocaleString('en-US', { maximumFractionDigits: 1 });
}

function renderPortfolioAudit(audit = {}) {
  const summary = audit.summary || {};
  const findings = Array.isArray(audit.findings) ? audit.findings : [];
  const reports = Array.isArray(audit.recent_reports) ? audit.recent_reports : [];
  const status = audit.status === 'clear' ? 'Clear' : audit.status === 'attention' ? 'Needs attention' : 'Needs review';
  return html`
    <div class="portfolio-audit-summary">
      ${raw(renderAuditMetric('Status', status))}
      ${raw(renderAuditMetric('Open items', summary.open_findings ?? 0))}
      ${raw(renderAuditMetric('Import reports', summary.import_reports ?? 0))}
      ${raw(renderAuditMetric('Pending Inbox', summary.pending_inbox_items ?? 0))}
    </div>
    <div class="portfolio-audit-findings">
      ${raw(findings.map(renderAuditFinding).join(''))}
    </div>
    ${reports.length ? html`
      <div class="portfolio-audit-reports">
        <h4>Recent import reports</h4>
        ${raw(renderAuditReports(reports))}
      </div>
    ` : html`<p class="fit-empty">No import reports recorded yet.</p>`}
  `;
}

function renderAuditMetric(label, value) {
  return html`
    <div class="portfolio-audit-metric">
      <span>${label}</span>
      <strong>${esc(String(value))}</strong>
    </div>
  `;
}

function renderAuditFinding(finding = {}) {
  const status = String(finding.status || 'clear');
  const severity = String(finding.severity || 'medium');
  const count = Number(finding.count || 0);
  return html`
    <article class="portfolio-audit-finding ${status} ${severity}">
      <div>
        <span class="portfolio-audit-kicker">${esc(finding.category || 'Audit')} · ${esc(labelize(severity))}</span>
        <h4>${esc(finding.title || 'Audit finding')}</h4>
        <p>${esc(finding.detail || '')}</p>
      </div>
      <div class="portfolio-audit-action">
        <strong>${count.toLocaleString('en-US')}</strong>
        ${finding.href ? html`<a class="action-link muted" href="${esc(finding.href)}">${esc(finding.action_label || 'Review')} <span class="arrow">→</span></a>` : ''}
      </div>
    </article>
  `;
}

function renderAuditReports(reports = []) {
  const columns = ['created_at', 'source_file_name', 'imported_activities', 'unresolved_count', 'duplicate_count'];
  return html`
    <div class="portfolio-maintenance-table" role="table" style="--maintenance-columns: ${columns.length};">
      <div class="portfolio-maintenance-row head" role="row">
        ${raw(columns.map(col => `<span role="columnheader">${esc(maintenanceColumnLabel(col))}</span>`).join(''))}
      </div>
      ${raw(reports.slice(0, 10).map(report => `
        <div class="portfolio-maintenance-row" role="row">
          ${columns.map(col => `<span role="cell">${esc(formatMaintenanceValue(report?.[col]))}</span>`).join('')}
        </div>
      `).join(''))}
    </div>
  `;
}

function renderAssetRegistryTools(maintenance = {}) {
  const query = String(maintenance?.payload?.query || '').trim();
  const count = Number(maintenance?.payload?.count || 0);
  return html`
    <form class="portfolio-registry-tools" data-asset-registry-search>
      <label class="fit-field">
        <span>Search assets</span>
        <input name="q" type="search" autocomplete="off" placeholder="Symbol, name, class, sector" value="${esc(query)}">
      </label>
      <button class="fit-review-button" type="submit">Search</button>
      <p class="portfolio-registry-count">${count.toLocaleString('en-US')} assets</p>
    </form>
  `;
}

function bindMaintenanceTools(root) {
  const registryForm = root.querySelector('[data-asset-registry-search]');
  if (registryForm) registryForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const data = new FormData(registryForm);
    const query = String(data.get('q') || '').trim();
    const params = new URLSearchParams({ section: 'assets' });
    if (query) params.set('q', query);
    location.hash = `portfolio?${params.toString()}`;
  });

  const riskForm = root.querySelector('[data-risk-policy-form]');
  if (riskForm) riskForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    await saveRiskGuardrails(riskForm);
  });
}

async function saveRiskGuardrails(form) {
  const statusEl = form.querySelector('[data-risk-policy-status]');
  const button = form.querySelector('button[type="submit"]');
  const data = new FormData(form);
  const body = {};
  for (const field of RISK_GUARDRAIL_FIELDS) {
    const rawValue = String(data.get(field.key) || '').trim();
    if (rawValue === '') continue;
    body[field.key] = Number(rawValue);
  }
  if (button) {
    button.disabled = true;
    button.textContent = 'Saving';
  }
  if (statusEl) {
    statusEl.textContent = 'Saving guardrails...';
    statusEl.classList.remove('error');
  }
  try {
    await api.updatePortfolioRiskPolicy(body);
    if (statusEl) statusEl.textContent = 'Saved. Refreshing current portfolio alerts...';
    await init({ section: 'risk-policy' });
  } catch (err) {
    if (statusEl) {
      statusEl.textContent = err?.message || 'Could not save guardrails.';
      statusEl.classList.add('error');
    }
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = 'Save guardrails';
    }
  }
}

function maintenanceRows(section, maintenance = {}) {
  if (Array.isArray(maintenance.rows)) return maintenance.rows.slice(0, 100);
  const payload = maintenance.payload && typeof maintenance.payload === 'object' ? maintenance.payload : {};
  if (section === 'prices') {
    const prices = payload.prices || payload.manual_prices || payload;
    return objectRows(prices, (symbol, item) => ({
      symbol,
      price: item?.price ?? item,
      note: item?.note || '',
      updated_at: item?.updated_at || item?.date || '',
    }));
  }
  if (section === 'fx') {
    const rates = payload.rates || payload.fx_rates || payload;
    return objectRows(rates, (currency, item) => ({
      currency,
      rate: item?.rate ?? item,
      base_currency: item?.base_currency || payload.base_currency || 'USD',
      updated_at: item?.updated_at || '',
    }));
  }
  if (section === 'cost-basis') {
    const methods = payload.methods || payload.cost_basis_methods || payload;
    return objectRows(methods, (scope, item) => ({
      scope,
      method: item?.method ?? item,
      account: item?.account || '',
      symbol: item?.symbol || '',
    }));
  }
  return [];
}

function objectRows(obj, mapRow) {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return [];
  return Object.entries(obj)
    .filter(([, value]) => value != null && typeof value !== 'function')
    .map(([key, value]) => mapRow(key, value));
}

function renderMaintenanceRows(section, rows) {
  const columnsBySection = {
    accounts: ['name', 'type', 'currency', 'id'],
    transactions: ['date', 'symbol', 'action', 'quantity', 'unit_price', 'account'],
    assets: ['quality_label', 'symbol', 'name', 'asset_class', 'asset_type', 'current_value', 'current_price', 'tags'],
    prices: ['symbol', 'price', 'note', 'updated_at'],
    fx: ['currency', 'rate', 'base_currency', 'updated_at'],
    'cost-basis': ['scope', 'method', 'account', 'symbol'],
  };
  const columns = columnsBySection[section] || Object.keys(rows[0] || {}).slice(0, 6);
  return html`
    <div class="portfolio-maintenance-table" role="table" style="--maintenance-columns: ${columns.length};">
      <div class="portfolio-maintenance-row head" role="row">
        ${raw(columns.map(col => `<span role="columnheader">${esc(maintenanceColumnLabel(col))}</span>`).join(''))}
      </div>
      ${raw(rows.slice(0, 25).map(row => `
        <div class="portfolio-maintenance-row" role="row">
          ${columns.map(col => `<span role="cell">${esc(formatMaintenanceValue(row?.[col]))}</span>`).join('')}
        </div>
      `).join(''))}
    </div>
  `;
}

function maintenanceColumnLabel(column) {
  return ({
    quality_label: 'Status',
    asset_class: 'Class',
    asset_type: 'Type',
    current_value: 'Value',
    current_price: 'Price',
    unit_price: 'Price',
    updated_at: 'Updated',
    base_currency: 'Base',
    created_at: 'Created',
    source_file_name: 'File',
    imported_activities: 'Imported',
    unresolved_count: 'Needs Review',
    duplicate_count: 'Duplicates',
  })[column] || labelize(column);
}

function maintenanceCopy(section) {
  return ({
    audit: 'A plain-English audit of recent imports, review items, asset readiness, prices, and cost basis follow-through.',
    accounts: 'Accounts created by imports or manual setup. Imported account names should land here before future review.',
    transactions: 'Recent portfolio activity created from applied imports and manual entries.',
    assets: 'A single searchable registry for holdings, watchlist names, custom assets, price overrides, and imported metadata.',
    prices: 'Manual quote overrides for assets that need local pricing evidence.',
    fx: 'Currency conversion rates used to keep portfolio values comparable.',
    'cost-basis': 'Lot accounting defaults used when imported transactions do not specify a method.',
    'risk-policy': 'Plain-language portfolio limits for concentration, account size, sector exposure, region exposure, and diversification depth.',
  })[section] || 'Portfolio maintenance records.';
}

function formatMaintenanceValue(value) {
  if (value == null || value === '') return '-';
  if (Array.isArray(value)) return value.join(', ') || '-';
  if (typeof value === 'number') {
    return Number.isFinite(value)
      ? value.toLocaleString('en-US', { maximumFractionDigits: 4 })
      : '-';
  }
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
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
