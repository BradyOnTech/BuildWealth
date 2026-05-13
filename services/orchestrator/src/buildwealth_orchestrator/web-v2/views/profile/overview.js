// Profile · Overview tab.
// A read-only summary that lets the user understand what's known without
// opening every editor. Numbers are derived from the profile payload only —
// nothing here writes data.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtUsd } from '../../lib/format.js';

export function renderOverview(ui) {
  const p = ui.profile || {};
  const tax = p.tax_profile || {};
  const flags = p.flags || {};
  const income = sumMonthly(p.income_items);
  const expenses = sumMonthly(p.expense_items);
  const householdMembers = Array.isArray(p.household_members) ? p.household_members : [];
  const surplus = income != null && expenses != null ? income - expenses : null;
  const debtTotal = sumField(p.debt_items, 'balance_usd');
  const goalsCount = (p.goal_items || []).length;
  const assetsTotal = sumField(p.physical_assets, 'current_value_usd');
  const runwayMonths = (income != null && expenses != null && expenses > 0)
    ? estimateRunway(p, expenses)
    : null;

  return html`
    <div class="profile-overview">
      ${raw(card('Household snapshot', [
        line('Household',        householdSummary(householdMembers), 'People this financial picture is built around.'),
        line('Monthly income',   fmtUsdOrEmpty(income),       'Sum of all income items entered.'),
        line('Monthly expenses', fmtUsdOrEmpty(expenses),     'Sum of all expense items entered.'),
        line('Monthly surplus',  fmtUsdOrEmpty(surplus),      surplus != null && surplus < 0 ? 'Spending exceeds income — cash runway is at risk.' : 'What is left to save or invest each month.'),
        line('Total debt',       flags.no_debt ? 'None tracked' : fmtUsdOrEmpty(debtTotal), flags.no_debt ? 'Marked as debt-free.' : 'Sum of outstanding balances.'),
        line('Goals',            goalsCount > 0 ? `${goalsCount} tracked` : (flags.no_goals ? 'Not tracking yet' : 'None added'), 'Add goals to drive plan and saving recommendations.'),
        line('Cash runway',      runwayMonths != null ? `${runwayMonths} mo` : 'Unknown',  'Months of expenses your liquid assets cover. Investment-fit advice depends on this.'),
      ]))}

      ${raw(card('Planning inputs', [
        line('Filing status',     humanFiling(tax.filing_status),                                'Used in tax-aware suggestions and Roth-conversion math.'),
        line('Marginal tax rate', fmtPctOrEmpty(tax.marginal_tax_rate),                          'Affects bonus, RSU, and tax-loss harvesting guidance.'),
        line('Effective tax rate',fmtPctOrEmpty(tax.effective_tax_rate),                        'Used in plan trajectory simulations.'),
        line('State',             tax.state ? esc(tax.state) : 'Not set',                       tax.state_tax_rate != null ? `State rate ${fmtPctOrEmpty(tax.state_tax_rate)}.` : 'State rate not set.'),
        line('Active plan',       p.notes ? 'Notes attached' : 'No plan-specific notes',        'Notes here travel with Copilot context.'),
      ]))}

      ${raw(card('Investment guardrails', [
        line('Single-investment limit',  guardrail(p, 'max_single_symbol_exposure_pct', 'pct'), 'Most of your portfolio BuildWealth should be comfortable seeing in one stock or fund.'),
        line('Minimum cash cushion',     guardrail(p, 'minimum_cash_runway_months', 'months'),  'Months of expenses you want available before taking more investment risk.'),
        line('Risk comfort',             guardrail(p, 'risk_tolerance', 'plain'),               'How much volatility you are willing to accept.'),
        line('Tax sensitivity',          guardrail(p, 'tax_sensitivity', 'plain'),              'How careful BuildWealth should be about taxable sales.'),
        line('Restricted investments',   restrictedSummary(p),                                  'Symbols or sectors BuildWealth should avoid suggesting.'),
      ], { footer: 'Edit guardrails on the Investing tab.' }))}

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

function estimateRunway(profile, monthlyExpenses) {
  // Conservative: only count physical assets explicitly flagged as liquid plus
  // any cash-buffer field on the profile. Holdings are tracked in Portfolio.
  const cash = Number(profile?.cash_buffer_usd);
  if (!Number.isFinite(cash) || cash <= 0) return null;
  return Math.max(0, Math.round(cash / monthlyExpenses));
}

/* ─────────────  Formatting  ───────────── */

function fmtUsdOrEmpty(value) {
  if (value == null) return null;
  return fmtUsd(value);
}

function fmtPctOrEmpty(value) {
  if (value == null || !Number.isFinite(Number(value))) return null;
  return `${(Number(value) * 100).toFixed(2)}%`;
}

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
