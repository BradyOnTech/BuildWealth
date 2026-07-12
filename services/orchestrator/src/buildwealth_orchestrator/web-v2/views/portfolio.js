// PORTFOLIO — three movements.
//   I.   The standing       — total value + performance
//   II.  The composition    — allocation strata + top holdings
//   III. Performance        — returns, benchmark comparison, attribution
//   IV.  The watch          — risk alerts or all-clear
// Footer — Look closer (native maintenance records and audit follow-through).

import { api } from '../lib/api.js';
import { state } from '../lib/state.js';
import { html, raw, $, esc, setView } from '../lib/dom.js';
import { skeleton } from '../lib/skeleton.js';
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
      api.portfolioAnalytics({ limit: 180, topN: 5, period: params.period || '1y' }).catch((err) => ({
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
    ${raw(renderSectionNav())}
    <div id="pf-standing" class="pf-section">${raw(renderStanding(data))}</div>
    <div id="pf-composition" class="pf-section">${raw(renderComposition(data))}</div>
    <div id="pf-performance" class="pf-section">${raw(renderAnalytics(analytics))}</div>
    <div id="pf-watch" class="pf-section">${raw(renderWatch(data))}</div>
    <div id="pf-fit" class="pf-section">${raw(renderFitReview(null, { initialSymbol: params.fit || '' }))}</div>
    <div id="pf-maintenance" class="pf-section">${raw(renderLookCloser(maintenanceSection, maintenance))}</div>
  `);
  bindSectionNav(root);
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

// Six labels to scan instead of six screens to scroll. Buttons, not hash
// links — the router owns the hash.
const PORTFOLIO_SECTIONS = [
  ['pf-standing', 'Standing'],
  ['pf-composition', 'Composition'],
  ['pf-performance', 'Performance'],
  ['pf-watch', 'The watch'],
  ['pf-fit', 'Fit review'],
  ['pf-maintenance', 'Maintenance'],
];

function renderSectionNav() {
  return html`
    <nav class="portfolio-toc" aria-label="Portfolio sections">
      ${raw(PORTFOLIO_SECTIONS.map(([id, label]) => html`
        <button type="button" data-pf-jump="${id}">${label}</button>
      `).join(''))}
    </nav>
  `;
}

function bindSectionNav(root) {
  root.querySelectorAll('[data-pf-jump]').forEach((button) => {
    button.addEventListener('click', () => {
      const target = root.querySelector(`#${button.dataset.pfJump}`);
      // Instant, not smooth: a jump nav is for finding things fast, and long
      // smooth scrolls stall on busy pages.
      if (target) target.scrollIntoView({ block: 'start' });
    });
  });
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
    { id: 'export', label: 'Export & Recovery', hint: 'Portfolio bundle and reversal posture' },
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
    export: 'export',
    recovery: 'export',
    bundle: 'export',
  };
  return aliases[value] || '';
}

async function loadMaintenanceSection(section, params = {}) {
  try {
    if (section === 'audit') return { section, payload: await api.portfolioAudit(25) };
    if (section === 'accounts') return { section, rows: await api.portfolioAccounts() };
    if (section === 'transactions') return { section, rows: await api.portfolioTransactions(100) };
    if (section === 'assets') {
      const [payload, selectedAsset] = await Promise.all([
        api.portfolioAssetSearch({ q: params.q || '', limit: 200 }),
        params.symbol ? api.portfolioAsset(params.symbol).catch((err) => ({ error: err?.message || 'Could not load this asset.' })) : Promise.resolve(null),
      ]);
      return { section, rows: payload.items || [], payload: { ...payload, selectedAsset } };
    }
    if (section === 'prices') return { section, payload: await api.portfolioManualPrices() };
    if (section === 'fx') return { section, payload: await api.portfolioFxRates() };
    if (section === 'cost-basis') return { section, payload: await api.portfolioCostBasisMethods() };
    if (section === 'risk-policy') return { section, payload: await api.portfolioRiskPolicy() };
    if (section === 'export') return { section, payload: await api.portfolioExportBundle(10_000) };
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
    : (section === 'audit' ? 'Portfolio Audit' : (section === 'risk-policy' ? 'Portfolio Guardrails' : (section === 'export' ? 'Export & Recovery' : labelize(section))));
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
      ${section === 'assets' ? raw(renderAssetDetail(maintenance?.payload?.selectedAsset)) : ''}
      ${section === 'assets' ? raw(renderCustomAssetTools()) : ''}
      ${section === 'prices' ? raw(renderManualPriceTools()) : ''}
      ${section === 'fx' ? raw(renderFxRateTools(maintenance?.payload || {})) : ''}
      ${section === 'risk-policy' ? raw(renderRiskGuardrails(maintenance)) : ''}
      ${section === 'export' ? raw(renderExportBundle(maintenance?.payload || {})) : ''}
      ${section === 'audit' || section === 'risk-policy' || section === 'export'
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
    ${raw(renderAuditEvents(audit.audit_events || []))}
    ${reports.length ? html`
      <div class="portfolio-audit-reports">
        <h4>Recent import reports</h4>
        ${raw(renderAuditReports(reports))}
      </div>
    ` : html`<p class="fit-empty">No import reports recorded yet.</p>`}
  `;
}

function renderAuditEvents(events = []) {
  const rows = Array.isArray(events) ? events.slice(0, 8) : [];
  if (!rows.length) return '';
  return html`
    <div class="portfolio-audit-reports">
      <h4>Audit event detail</h4>
      <div class="portfolio-audit-findings">
        ${raw(rows.map(event => `
          <article class="portfolio-audit-finding ${esc(event.status || 'clear')} ${esc(event.severity || 'low')}">
            <div>
              <span class="portfolio-audit-kicker">${esc(labelize(event.kind || 'event'))} · ${esc(labelize(event.severity || 'low'))}</span>
              <h4>${esc(event.title || 'Audit event')}</h4>
              <p>${esc(event.detail || '')}</p>
              ${event.recovery_note ? `<p>${esc(event.recovery_note)}</p>` : ''}
            </div>
            <div class="portfolio-audit-action">
              ${event.href ? `<a class="action-link muted" href="${esc(event.href)}">${esc(event.action_label || 'Review')} <span class="arrow">→</span></a>` : ''}
            </div>
          </article>
        `).join(''))}
      </div>
    </div>
  `;
}

function renderExportBundle(bundle = {}) {
  const summary = bundle.summary || {};
  const posture = bundle.recovery_posture || {};
  return html`
    <div class="portfolio-audit-summary">
      ${raw(renderAuditMetric('Transactions', summary.transactions ?? 0))}
      ${raw(renderAuditMetric('Holdings', summary.holdings ?? 0))}
      ${raw(renderAuditMetric('Lots', summary.lots ?? 0))}
      ${raw(renderAuditMetric('Import reports', summary.import_reports ?? 0))}
      ${raw(renderAuditMetric('Audit events', summary.audit_events ?? 0))}
    </div>
    <div class="settings-test-block pass">
      <p class="settings-test-headline">Bundle export is ready</p>
      <p class="settings-test-detail">
        Includes transactions, holdings, lots, asset metadata, manual prices, FX rates,
        cost-basis rules, import reports, and the latest portfolio audit report.
      </p>
      <a class="link-editorial" href="/api/portfolio/export-bundle" target="_blank" rel="noopener">Open JSON export bundle</a>
    </div>
    <div class="portfolio-audit-findings">
      ${raw(Object.entries(posture).map(([label, detail]) => `
        <article class="portfolio-audit-finding clear low">
          <div>
            <span class="portfolio-audit-kicker">Recovery</span>
            <h4>${esc(labelize(label))}</h4>
            <p>${esc(detail)}</p>
          </div>
        </article>
      `).join(''))}
    </div>
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
  const columns = ['created_at', 'source_file_name', 'imported_activities', 'unresolved_count', 'duplicate_count', 'report'];
  return html`
    <div class="portfolio-maintenance-table" role="table" style="--maintenance-columns: ${columns.length};">
      <div class="portfolio-maintenance-row head" role="row">
        ${raw(columns.map(col => `<span role="columnheader">${esc(maintenanceColumnLabel(col))}</span>`).join(''))}
      </div>
      ${raw(reports.slice(0, 10).map(report => `
        <div class="portfolio-maintenance-row" role="row">
          ${columns.slice(0, -1).map(col => `<span role="cell">${esc(formatMaintenanceValue(report?.[col]))}</span>`).join('')}
          <span role="cell" class="portfolio-audit-report-links">
            ${report?.href ? `<a class="action-link muted" href="${esc(report.href)}">Open report</a>` : ''}
            ${report?.portfolio_history_href ? `<a class="action-link muted" href="${esc(report.portfolio_history_href)}">History</a>` : ''}
          </span>
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

function renderAssetDetail(asset) {
  if (!asset) return '';
  if (asset.error) {
    return html`<p class="inline-warning">${esc(asset.error)}</p>`;
  }
  const provenance = Array.isArray(asset.provenance) ? asset.provenance : [];
  const manual = asset.manual_price_detail && typeof asset.manual_price_detail === 'object' ? asset.manual_price_detail : {};
  return html`
    <section class="portfolio-asset-detail">
      <header class="portfolio-asset-detail-head">
        <div>
          <span class="portfolio-audit-kicker">${esc(asset.quality_label || 'Asset detail')}</span>
          <h4>${esc(asset.symbol || '')} · ${esc(asset.name || 'Unnamed asset')}</h4>
          <p>
            ${esc([asset.asset_class, asset.asset_type, asset.sector, asset.region].filter(Boolean).join(' · ') || 'Metadata needs review.')}
          </p>
        </div>
        <a class="action-link muted" href="#research?symbol=${encodeURIComponent(asset.symbol || '')}">Open research</a>
      </header>
      <div class="portfolio-audit-summary">
        ${raw(renderAuditMetric('Value', formatMaintenanceValue(asset.current_value)))}
        ${raw(renderAuditMetric('Price', formatMaintenanceValue(asset.current_price)))}
        ${raw(renderAuditMetric('Source', asset.price_source || 'Not set'))}
        ${raw(renderAuditMetric('Accounts', Array.isArray(asset.accounts) ? asset.accounts.length : 0))}
      </div>
      ${provenance.length ? html`
        <div class="portfolio-provenance-list">
          ${raw(provenance.map(item => `
            <article>
              <strong>${esc(item.label || labelize(item.source))}</strong>
              <span>${esc(item.detail || '')}</span>
              ${item.updated_at ? `<code>${esc(item.updated_at)}</code>` : ''}
            </article>
          `).join(''))}
        </div>
      ` : html`<p class="fit-empty">No source history is recorded for this asset yet.</p>`}
      ${manual.price ? html`
        <div class="settings-test-block pass">
          <p class="settings-test-headline">Manual price override is active</p>
          <p class="settings-test-detail">
            ${esc(asset.symbol)} is using ${esc(formatMaintenanceValue(manual.price))}
            ${manual.note ? ` · ${esc(manual.note)}` : ''}. Clear it from Manual prices when live or imported pricing is ready.
          </p>
        </div>
      ` : ''}
      <form class="portfolio-asset-metadata-form" data-asset-metadata-form data-symbol="${esc(asset.symbol || '')}">
        ${raw(assetMetadataField('name', 'Name', asset.name))}
        ${raw(assetMetadataField('asset_class', 'Class', asset.asset_class))}
        ${raw(assetMetadataField('asset_type', 'Type', asset.asset_type))}
        ${raw(assetMetadataField('sector', 'Sector', asset.sector))}
        ${raw(assetMetadataField('region', 'Region', asset.region))}
        ${raw(assetMetadataField('metadata_source', 'Source note', asset.metadata_source || 'manual_review'))}
        <button class="fit-review-button" type="submit">Save asset metadata</button>
        <p class="portfolio-guardrails-status" data-asset-metadata-status>
          This updates the local BuildWealth asset record.
        </p>
      </form>
    </section>
  `;
}

function assetMetadataField(name, label, value) {
  return html`
    <label class="fit-field">
      <span>${esc(label)}</span>
      <input name="${esc(name)}" type="text" value="${esc(value || '')}">
    </label>
  `;
}

function renderCustomAssetTools() {
  return html`
    <form class="portfolio-custom-asset-form" data-custom-asset-form>
      <label class="fit-field"><span>Custom asset name</span><input name="name" type="text" placeholder="Private fund, property, collectible"></label>
      <label class="fit-field"><span>Value</span><input name="value" type="number" step="0.01" min="0.01" placeholder="25000"></label>
      <label class="fit-field"><span>Symbol</span><input name="symbol" type="text" placeholder="Optional"></label>
      <label class="fit-field"><span>Class</span><input name="asset_class" type="text" placeholder="Alternatives"></label>
      <label class="fit-field"><span>Type</span><input name="asset_type" type="text" placeholder="custom_asset"></label>
      <label class="fit-field"><span>Account</span><input name="account" type="text" placeholder="default"></label>
      <button class="fit-review-button" type="submit">Add custom asset</button>
      <p class="portfolio-guardrails-status" data-custom-asset-status>
        Adds a local asset, a portfolio history entry, and a manual price.
      </p>
    </form>
  `;
}

function renderManualPriceTools() {
  return html`
    <form class="portfolio-manual-price-form" data-manual-price-form>
      <label class="fit-field"><span>Symbol</span><input name="symbol" type="text" placeholder="VTI"></label>
      <label class="fit-field"><span>Price</span><input name="price" type="number" step="0.0001" min="0.0001" placeholder="250.00"></label>
      <label class="fit-field span-2"><span>Note</span><input name="note" type="text" placeholder="Source or reason for this override"></label>
      <button class="fit-review-button" type="submit">Save manual price</button>
      <p class="portfolio-guardrails-status" data-manual-price-status>
        Manual prices are local overrides and can be cleared from the table below.
      </p>
    </form>
  `;
}

function renderFxRateTools(payload = {}) {
  const base = payload.base_currency || 'USD';
  return html`
    <form class="portfolio-fx-rate-form" data-fx-rate-form>
      <label class="fit-field"><span>Currency</span><input name="currency" type="text" maxlength="8" placeholder="EUR"></label>
      <label class="fit-field"><span>Rate to ${esc(base)}</span><input name="rate" type="number" step="0.00000001" min="0.00000001" placeholder="1.08"></label>
      <input name="base_currency" type="hidden" value="${esc(base)}">
      <button class="fit-review-button" type="submit">Save FX rate</button>
      <p class="portfolio-guardrails-status" data-fx-rate-status>
        Non-base rates can be cleared; the base currency stays fixed.
      </p>
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

  const metadataForm = root.querySelector('[data-asset-metadata-form]');
  if (metadataForm) metadataForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    await saveAssetMetadata(metadataForm);
  });

  const customAssetForm = root.querySelector('[data-custom-asset-form]');
  if (customAssetForm) customAssetForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    await saveCustomAsset(customAssetForm);
  });

  const manualPriceForm = root.querySelector('[data-manual-price-form]');
  if (manualPriceForm) manualPriceForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    await saveManualPrice(manualPriceForm);
  });

  const fxRateForm = root.querySelector('[data-fx-rate-form]');
  if (fxRateForm) fxRateForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    await saveFxRate(fxRateForm);
  });

  root.querySelectorAll('[data-clear-manual-price]').forEach((button) => {
    button.addEventListener('click', async (event) => {
      event.preventDefault();
      const symbol = button.getAttribute('data-clear-manual-price');
      if (!symbol) return;
      button.disabled = true;
      button.textContent = 'Clearing';
      await api.clearPortfolioManualPrice(symbol);
      await init({ section: 'prices' });
    });
  });

  root.querySelectorAll('[data-clear-fx-rate]').forEach((button) => {
    button.addEventListener('click', async (event) => {
      event.preventDefault();
      const currency = button.getAttribute('data-clear-fx-rate');
      if (!currency) return;
      button.disabled = true;
      button.textContent = 'Clearing';
      await api.clearPortfolioFxRate(currency);
      await init({ section: 'fx' });
    });
  });
}

async function saveAssetMetadata(form) {
  const symbol = String(form.getAttribute('data-symbol') || '').trim().toUpperCase();
  const statusEl = form.querySelector('[data-asset-metadata-status]');
  const button = form.querySelector('button[type="submit"]');
  const data = new FormData(form);
  const body = {};
  for (const key of ['name', 'asset_class', 'asset_type', 'sector', 'region', 'metadata_source']) {
    const value = String(data.get(key) || '').trim();
    if (value) body[key] = value;
  }
  await submitMaintenanceForm({
    statusEl,
    button,
    savingText: 'Saving',
    savedText: 'Saved. Reloading asset detail...',
    defaultButtonText: 'Save asset metadata',
    action: () => api.updatePortfolioAssetMetadata(symbol, body),
    refresh: () => init({ section: 'assets', symbol }),
  });
}

async function saveCustomAsset(form) {
  const statusEl = form.querySelector('[data-custom-asset-status]');
  const button = form.querySelector('button[type="submit"]');
  const data = new FormData(form);
  const body = {};
  for (const key of ['name', 'symbol', 'asset_class', 'asset_type', 'account']) {
    const value = String(data.get(key) || '').trim();
    if (value) body[key] = value;
  }
  body.value = Number(data.get('value'));
  await submitMaintenanceForm({
    statusEl,
    button,
    savingText: 'Adding',
    savedText: 'Custom asset added. Reloading registry...',
    defaultButtonText: 'Add custom asset',
    action: () => api.createPortfolioCustomAsset(body),
    refresh: (result) => init({ section: 'assets', symbol: result?.symbol || body.symbol || '' }),
  });
}

async function saveManualPrice(form) {
  const statusEl = form.querySelector('[data-manual-price-status]');
  const button = form.querySelector('button[type="submit"]');
  const data = new FormData(form);
  const symbol = String(data.get('symbol') || '').trim().toUpperCase();
  await submitMaintenanceForm({
    statusEl,
    button,
    savingText: 'Saving',
    savedText: 'Manual price saved. Reloading prices...',
    defaultButtonText: 'Save manual price',
    action: () => api.setPortfolioManualPrice({
      symbol,
      price: Number(data.get('price')),
      note: String(data.get('note') || '').trim(),
    }),
    refresh: () => init({ section: 'prices' }),
  });
}

async function saveFxRate(form) {
  const statusEl = form.querySelector('[data-fx-rate-status]');
  const button = form.querySelector('button[type="submit"]');
  const data = new FormData(form);
  await submitMaintenanceForm({
    statusEl,
    button,
    savingText: 'Saving',
    savedText: 'FX rate saved. Reloading rates...',
    defaultButtonText: 'Save FX rate',
    action: () => api.setPortfolioFxRate({
      currency: String(data.get('currency') || '').trim().toUpperCase(),
      rate: Number(data.get('rate')),
      base_currency: String(data.get('base_currency') || '').trim().toUpperCase(),
    }),
    refresh: () => init({ section: 'fx' }),
  });
}

async function submitMaintenanceForm({ statusEl, button, savingText, savedText, defaultButtonText, action, refresh }) {
  if (button) {
    button.disabled = true;
    button.textContent = savingText;
  }
  if (statusEl) {
    statusEl.textContent = `${savingText}...`;
    statusEl.classList.remove('error');
  }
  try {
    const result = await action();
    if (statusEl) statusEl.textContent = savedText;
    await refresh(result);
  } catch (err) {
    if (statusEl) {
      statusEl.textContent = err?.message || 'Could not save this change.';
      statusEl.classList.add('error');
    }
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = defaultButtonText;
    }
  }
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
    const prices = payload.by_symbol || payload.prices || payload.manual_prices || payload;
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
    assets: ['quality_label', 'symbol', 'name', 'asset_class', 'asset_type', 'current_value', 'current_price', 'tags', 'detail'],
    prices: ['symbol', 'price', 'note', 'updated_at', 'actions'],
    fx: ['currency', 'rate', 'base_currency', 'updated_at', 'actions'],
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
          ${columns.map(col => `<span role="cell">${raw(formatMaintenanceCell(section, col, row))}</span>`).join('')}
        </div>
      `).join(''))}
    </div>
  `;
}

function formatMaintenanceCell(section, column, row = {}) {
  if (section === 'assets' && column === 'symbol') {
    const symbol = String(row?.symbol || '').trim().toUpperCase();
    return symbol
      ? `<a class="action-link muted" href="#portfolio?section=assets&symbol=${encodeURIComponent(symbol)}">${esc(symbol)}</a>`
      : '-';
  }
  if (section === 'assets' && column === 'detail') {
    const symbol = String(row?.symbol || '').trim().toUpperCase();
    return symbol
      ? `<a class="action-link muted" href="#portfolio?section=assets&symbol=${encodeURIComponent(symbol)}">Details</a>`
      : '-';
  }
  if (section === 'prices' && column === 'actions') {
    const symbol = String(row?.symbol || '').trim().toUpperCase();
    return symbol
      ? `<button class="action-link muted" type="button" data-clear-manual-price="${esc(symbol)}">Clear</button>`
      : '-';
  }
  if (section === 'fx' && column === 'actions') {
    const currency = String(row?.currency || '').trim().toUpperCase();
    const base = String(row?.base_currency || '').trim().toUpperCase();
    return currency && currency !== base
      ? `<button class="action-link muted" type="button" data-clear-fx-rate="${esc(currency)}">Clear</button>`
      : '-';
  }
  return esc(formatMaintenanceValue(row?.[column]));
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
    detail: 'Detail',
    actions: 'Actions',
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
    export: 'Export a complete portfolio evidence bundle and review how manual, imported, and destructive changes can be recovered.',
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
      ${skeleton('120px')}
    </section>
  `;
}
