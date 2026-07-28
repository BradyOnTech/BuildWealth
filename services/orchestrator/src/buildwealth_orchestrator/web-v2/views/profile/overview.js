// Profile · Overview tab.
// A read-only summary that lets the user understand what's known without
// opening every editor. Numbers are derived from the profile payload only —
// nothing here writes data.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtUsdOrEmpty, fmtPctOrDash } from '../../lib/format.js';
import { renderDocumentCapture } from './document_capture.js';

// The capture card is part of the overview surface; re-exported so callers
// and tests can reach it without knowing the file split.
export { renderDocumentCapture } from './document_capture.js';

export function renderOverview(ui) {
  const p = ui.profile || {};
  const health = ui.financialHealth || {};
  const tax = p.tax_profile || {};
  const flags = p.flags || {};
  const income = finiteOr(health.gross_monthly_income_usd, sumMonthly(p.income_items));
  const expenses = finiteOr(
    health.total_monthly_expenses_usd,
    sumMonthly((p.expense_items || []).filter(item => !item?.linked_debt_id)),
  );
  const estimatedTaxes = finiteOr(health.estimated_monthly_taxes_usd, null);
  const debtPayments = finiteOr(health.total_monthly_debt_payments_usd, null);
  const householdMembers = Array.isArray(p.household_members) ? p.household_members : [];
  const surplus = finiteOr(
    health.monthly_surplus_usd,
    income != null && expenses != null ? income - expenses : null,
  );
  const debtTotal = sumField(p.debt_items, 'balance_usd');
  const goalsCount = (p.goal_items || []).length;
  const assetsTotal = sumOwnedAssets(p.physical_assets);
  const planFundingAssets = finiteOr(
    health.plan_funding_assets_usd,
    sumOwnedAssets((p.physical_assets || []).filter(asset => asset.include_in_plan_funding)),
  );
  const runwayMonths = (income != null && expenses != null && expenses > 0)
    ? estimateRunway(p, expenses)
    : null;

  return html`
    <div class="profile-overview">
      ${raw(card('Household snapshot', [
        line('Household',        householdSummary(householdMembers), 'People this financial picture is built around.'),
        line('Gross monthly income', fmtUsdOrEmpty(income),       'Sum of all income items entered before estimated taxes.'),
        line('Estimated monthly taxes', fmtUsdOrEmpty(estimatedTaxes), 'Uses saved effective federal and state tax rates for pre-tax income.'),
        line('Monthly living expenses', fmtUsdOrEmpty(expenses),     'Recurring expenses entered in the Profile.'),
        line('Minimum debt payments', fmtUsdOrEmpty(debtPayments), 'Required monthly debt payments entered in the Profile.'),
        line('After-tax surplus',  fmtUsdOrEmpty(surplus),      surplus != null && surplus < 0 ? 'Spending exceeds after-tax income — cash runway is at risk.' : 'What is left after estimated taxes, living expenses, and minimum debt payments.'),
        line('Total debt',       flags.no_debt ? 'None tracked' : fmtUsdOrEmpty(debtTotal), flags.no_debt ? 'Marked as debt-free.' : 'Sum of outstanding balances.'),
        line('Goals',            goalsCount > 0 ? `${goalsCount} tracked` : (flags.no_goals ? 'Not tracking yet' : 'None added'), 'Add goals to drive plan and saving recommendations.'),
        line('Cash runway',      runwayMonths != null ? `${runwayMonths} mo` : 'Unknown',  'Months of expenses your liquid assets cover. Investment-fit advice depends on this.'),
      ]))}

      ${raw(card('Planning inputs', [
        line('Filing status',     humanFiling(tax.filing_status),                                'Used in tax-aware suggestions and Roth-conversion math.'),
        line('Marginal tax rate', fmtPctOrDash(tax.marginal_tax_rate, null),                     'Affects bonus, RSU, and tax-loss harvesting guidance.'),
        line('Effective tax rate',fmtPctOrDash(tax.effective_tax_rate, null),                   'Used in plan trajectory simulations.'),
        line('State',             tax.state ? esc(tax.state) : 'Not set',                       tax.state_tax_rate != null ? `State rate ${fmtPctOrDash(tax.state_tax_rate, null)}.` : 'State rate not set.'),
        line('Active plan',       p.notes ? 'Notes attached' : 'No plan-specific notes',        'Notes here travel with Copilot context.'),
      ]))}

      ${raw(card('Protection & property', [
        line('Property and vehicles', assetsTotal == null ? 'None tracked' : fmtUsdOrEmpty(assetsTotal), 'Included in net worth; not treated as liquid cash.'),
        line('Available to fund the plan', planFundingAssets == null ? 'None designated' : fmtUsdOrEmpty(planFundingAssets), 'Only property you explicitly make available is considered a possible funding source.'),
        line('Insurance policies', `${(p.insurance_policies || []).length} tracked`, 'Coverage lives here; premiums remain linked Expenses.'),
        line('Benefits', `${(p.benefit_items || []).length} tracked`, 'Employer and public benefits inform planning without being counted as current cash.'),
        line('Estate documents', estateSummary(p.estate_readiness), 'Readiness only—BuildWealth does not store legal document contents here.'),
      ], { footer: 'Review property, insurance, benefits, and estate readiness in their Profile tabs.' }))}

      ${raw(renderLifeChangeGuide(p))}

      ${raw(card('Investment guardrails', [
        line('Single-investment limit',  guardrail(p, 'max_single_symbol_exposure_pct', 'pct'), 'Most of your portfolio BuildWealth should be comfortable seeing in one stock or fund.'),
        line('Minimum cash cushion',     guardrail(p, 'minimum_cash_runway_months', 'months'),  'Months of expenses you want available before taking more investment risk.'),
        line('Risk comfort',             guardrail(p, 'risk_tolerance', 'plain'),               'How much volatility you are willing to accept.'),
        line('Tax sensitivity',          guardrail(p, 'tax_sensitivity', 'plain'),              'How careful BuildWealth should be about taxable sales.'),
        line('Restricted investments',   restrictedSummary(p),                                  'Symbols or sectors BuildWealth should avoid suggesting.'),
      ], { footer: 'Edit guardrails on the Investing tab.' }))}

      ${raw(renderDocumentCapture())}

      ${raw(renderRegistrationCard(ui))}

      ${raw(needsReviewCard(ui))}
    </div>
  `;
}

/* ─────────────  Cards  ───────────── */

function card(title, lines, opts = {}) {
  const items = lines.map(line => `
    <li class="profile-line ${line.tone || ''}">
      <span class="profile-line-label">${esc(line.label)}</span>
      <span class="profile-line-value">${esc(line.value)}</span>
      ${line.detail ? `<span class="profile-line-detail">${esc(line.detail)}</span>` : ''}
    </li>
  `).join('');

  return html`
    <article class="profile-card">
      <header class="profile-card-head">
        <h3 class="profile-card-title">${title}</h3>
      </header>
      <ul class="profile-line-list">
        ${raw(items)}
      </ul>
      ${opts.footer ? html`<footer class="profile-card-foot">${opts.footer}</footer>` : ''}
    </article>
  `;
}

function line(label, value, detail) {
  return { label, value: value || '—', detail };
}

function estateSummary(estate) {
  if (!estate || typeof estate !== 'object') return 'Not reviewed';
  const keys = ['will_status', 'trust_status', 'power_of_attorney_status', 'healthcare_directive_status'];
  const complete = keys.filter(key => estate[key] === 'complete').length;
  const answered = keys.filter(key => estate[key] && estate[key] !== 'unknown').length;
  if (!answered) return 'Not reviewed';
  return `${complete} of ${keys.length} complete`;
}

function needsReviewCard(ui) {
  const candidates = ui.candidates || [];
  if (!candidates.length) {
    return html`
      <article class="profile-card profile-card-quiet">
        <header class="profile-card-head">
          <h3 class="profile-card-title">Needs review</h3>
        </header>
        <p class="profile-card-empty">
          Nothing pending. BuildWealth has no unresolved suggestions about your profile right now.
        </p>
      </article>
    `;
  }

  const items = candidates.slice(0, 5).map(c => `
    <li class="profile-review-item">
      <span class="profile-review-tag">${esc(humanCandidateKind(c))}</span>
      <span class="profile-review-headline">${esc(c.headline || c.title || 'Suggested context update')}</span>
      <span class="profile-review-meta">${esc(c.detail || c.summary || '')}</span>
    </li>
  `).join('');

  return html`
    <article class="profile-card profile-card-attn">
      <header class="profile-card-head">
        <h3 class="profile-card-title">Needs review</h3>
        <span class="profile-card-count">${candidates.length}</span>
      </header>
      <ul class="profile-review-list">
        ${raw(items)}
      </ul>
      <footer class="profile-card-foot">
        <a class="link-editorial" href="#inbox" data-route>Open Inbox</a>
      </footer>
    </article>
  `;
}

export function renderRegistrationCard(ui = {}) {
  const progress = ui.onboardingProgress || {};
  const started = progress.started === true;
  const complete = progress.status === 'complete';
  const journeyLabel = !started
    ? 'Setup has not been started for this workspace.'
    : complete
      ? 'Your first setup journey is complete. You can review it without changing current data.'
      : 'Your setup journey is still in progress and will resume where you left it.';
  return html`
    <article class="profile-card profile-registration-card">
      <header class="profile-card-head">
        <div>
          <p class="profile-card-kicker">Registration &amp; setup</p>
          <h3 class="profile-card-title">Your first financial picture</h3>
        </div>
      </header>
      <p class="profile-card-empty">${journeyLabel}</p>
      <div class="profile-registration-actions">
        <a class="btn btn-quiet" href="#setup" data-route>
          ${complete ? 'Review setup journey' : 'Continue setup'}
        </a>
        <button class="link-editorial danger" type="button" data-profile-reset-open>
          Reset financial data &amp; register again
        </button>
      </div>
      <p class="profile-registration-note">
        Resetting keeps your BuildWealth sign-in and household ownership. It creates a recovery backup,
        clears this workspace’s financial data, and starts Setup again from the beginning.
      </p>
    </article>
  `;
}

function renderLifeChangeGuide(profile) {
  const members = Array.isArray(profile.household_members) ? profile.household_members : [];
  const expenses = Array.isArray(profile.expense_items) ? profile.expense_items : [];
  const debts = Array.isArray(profile.debt_items) ? profile.debt_items : [];
  const goals = Array.isArray(profile.goal_items) ? profile.goal_items : [];
  const assets = Array.isArray(profile.physical_assets) ? profile.physical_assets : [];
  const tax = profile.tax_profile || {};
  const transitions = [];

  if (members.some(member => String(member?.relationship || '').toLowerCase() === 'partner')) {
    const marriedTax = String(tax.filing_status || '').startsWith('married_');
    transitions.push({
      title: 'Partner or marriage',
      detail: marriedTax
        ? 'Household and tax status agree. Review income, shared expenses, and goals when they change.'
        : 'A partner is saved, but filing status is not married. Review only the connected sections—no need to restart setup.',
      tasks: [
        task(true, 'Partner in household', 'household'),
        task(marriedTax, 'Filing status reviewed', 'taxes'),
        task((profile.income_items || []).length > 1, 'Household income reviewed', 'income'),
        task(Boolean(profile.flags?.expenses_complete), 'Shared expenses confirmed', 'expenses'),
        task(hasKeyword(goals, ['wedding', 'marriage']), 'Related goal reviewed', 'goals', true),
      ],
    });
  }

  if (members.some(member => ['child', 'dependent'].includes(String(member?.relationship || '').toLowerCase()))) {
    transitions.push({
      title: 'Child or new dependent',
      detail: 'Keep the household change connected to childcare, leave, insurance-sized expenses, and a dated cash goal.',
      tasks: [
        task(true, 'Dependent in household', 'household'),
        task(hasKeyword(expenses, ['child', 'daycare', 'care', 'school']), 'Child-related expenses reviewed', 'expenses'),
        task(hasKeyword(goals, ['child', 'baby', 'college', 'education']), 'Dated child goal reviewed', 'goals'),
        task((profile.income_items || []).length > 0, 'Leave or income step-down reviewed', 'income', true),
      ],
    });
  }

  if (assets.some(asset => String(asset?.asset_type || '').toLowerCase() === 'real_estate')) {
    const hasMortgage = hasKeyword(debts, ['mortgage', 'home loan']);
    const hasRent = hasKeyword(expenses, ['rent']);
    transitions.push({
      title: 'Home purchase',
      detail: 'The property is saved. Finish the connected debt and housing-cost changes so net worth and cash flow move together.',
      tasks: [
        task(true, 'Property asset recorded', 'assets'),
        task(hasMortgage, 'Mortgage or financing reviewed', 'debt'),
        task(!hasRent, 'Rent removed or end-dated', 'expenses'),
        task(hasKeyword(expenses, ['mortgage', 'property tax', 'home insurance', 'hoa']), 'Ongoing home costs reviewed', 'expenses'),
      ],
    });
  }

  return html`
    <article class="profile-card ${transitions.some(item => item.tasks.some(row => !row.done && !row.optional)) ? 'profile-card-attn' : ''}">
      <header class="profile-card-head">
        <h3 class="profile-card-title">Life changes</h3>
      </header>
      ${transitions.length ? raw(transitions.map(transition => html`
        <section class="profile-life-transition">
          <h4>${esc(transition.title)}</h4>
          <p class="profile-card-empty">${esc(transition.detail)}</p>
          <ul class="profile-review-list">
            ${raw(transition.tasks.map(row => html`
              <li class="profile-review-item">
                <span class="profile-review-tag">${row.done ? 'Done' : row.optional ? 'Optional' : 'Review'}</span>
                <span class="profile-review-headline">${esc(row.label)}</span>
                <a class="link-editorial" href="#profile?section=${esc(row.section)}" data-route>${row.done ? 'Open' : 'Review now'}</a>
              </li>
            `).join(''))}
          </ul>
        </section>
      `).join('')) : html`
        <p class="profile-card-empty">No connected transition is in progress. When a partner, dependent, or home is added, the related checklist appears here.</p>
      `}
      <footer class="profile-card-foot">
        <a class="link-editorial" href="#profile?section=goals" data-route>Plan a future life event</a>
        <span class="marginalia">Draft goals and preview Plan what-ifs before saving anything durable.</span>
      </footer>
    </article>
  `;
}

function task(done, label, section, optional = false) {
  return { done: Boolean(done), label, section, optional };
}

function hasKeyword(items, keywords) {
  return (Array.isArray(items) ? items : []).some(item => {
    const text = `${item?.label || ''} ${item?.category || ''} ${item?.notes || ''}`.toLowerCase();
    return keywords.some(keyword => text.includes(keyword));
  });
}

/* ─────────────  Aggregations  ───────────── */

function sumMonthly(items) {
  if (!Array.isArray(items) || !items.length) return null;
  let total = 0;
  let any = false;
  for (const item of items) {
    const amount = Number(item?.monthly_amount_usd);
    if (Number.isFinite(amount)) {
      total += amount;
      any = true;
    }
  }
  return any ? total : null;
}

function sumField(items, key) {
  if (!Array.isArray(items) || !items.length) return null;
  let total = 0;
  let any = false;
  for (const item of items) {
    const v = Number(item?.[key]);
    if (Number.isFinite(v)) { total += v; any = true; }
  }
  return any ? total : null;
}

function sumOwnedAssets(items) {
  if (!Array.isArray(items) || !items.length) return null;
  return items.reduce((total, item) => {
    const value = Number(item?.current_value_usd);
    const ownership = Number(item?.ownership_pct ?? 100);
    if (!Number.isFinite(value) || !Number.isFinite(ownership)) return total;
    return total + value * Math.min(Math.max(ownership, 0), 100) / 100;
  }, 0);
}

function finiteOr(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function estimateRunway(profile, monthlyExpenses) {
  // Conservative: only count physical assets explicitly flagged as liquid plus
  // any cash-buffer field on the profile. Holdings are tracked in Portfolio.
  const cash = Number(profile?.cash_buffer_usd);
  if (!Number.isFinite(cash) || cash <= 0) return null;
  return Math.max(0, Math.round(cash / monthlyExpenses));
}

/* ─────────────  Formatting  ───────────── */

function humanFiling(value) {
  if (!value) return null;
  return String(value).replace(/_/g, ' ');
}

function guardrail(profile, key, kind) {
  const policy = profile?.investment_policy || {};
  const value = policy[key];
  if (value == null || value === '') return null;
  if (kind === 'pct') {
    const num = Number(value);
    if (!Number.isFinite(num)) return String(value);
    return num <= 1 ? `${(num * 100).toFixed(0)}% max` : `${num}% max`;
  }
  if (kind === 'months') return `${value} months`;
  return String(value).replace(/_/g, ' ');
}

function restrictedSummary(profile) {
  const policy = profile?.investment_policy || {};
  const symbols = Array.isArray(policy.restricted_symbols) ? policy.restricted_symbols : [];
  const sectors = Array.isArray(policy.restricted_sectors) ? policy.restricted_sectors : [];
  if (!symbols.length && !sectors.length) return 'None set';
  const total = symbols.length + sectors.length;
  return `${total} restricted${symbols.length ? ` (${symbols.slice(0, 3).join(', ')}${symbols.length > 3 ? '…' : ''})` : ''}`;
}

function humanCandidateKind(candidate) {
  const kind = candidate?.field_path || candidate?.kind || 'context';
  return String(kind).replace(/[._]/g, ' ');
}

function householdSummary(members) {
  if (!Array.isArray(members) || !members.length) return 'Not set';
  const adults = members.filter(member => !member?.dependent && !['child', 'dependent'].includes(String(member?.relationship || '').toLowerCase())).length;
  const dependents = members.length - adults;
  const parts = [];
  if (adults > 0) parts.push(`${adults} adult${adults === 1 ? '' : 's'}`);
  if (dependents > 0) parts.push(`${dependents} dependent${dependents === 1 ? '' : 's'}`);
  return parts.length ? parts.join(', ') : `${members.length} member${members.length === 1 ? '' : 's'}`;
}
