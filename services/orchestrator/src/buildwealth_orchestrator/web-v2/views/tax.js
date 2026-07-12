// TAX STRATEGY.
// Two decision-support tools composed from the household's own data:
// tax-loss harvesting candidates (taxable lots below basis, wash-sale aware)
// and a fill-the-bracket Roth conversion ladder priced by the tax engine.

import { api } from '../lib/api.js';
import { html, raw, $, esc, setView } from '../lib/dom.js';
import { fmtUsd, fmtUsdOrDash } from '../lib/format.js';
import { skeleton } from '../lib/skeleton.js';

export const meta = {
  id: 'tax',
  label: 'Tax Strategy',
  numeral: '·',
  group: 'utility',
};

const ui = {
  harvest: null,
  harvestError: null,
  ladder: null,
  ladderError: null,
  ladderBusy: false,
  draft: {
    traditional_balance_usd: '',
    annual_ordinary_income_usd: '',
    target_bracket_rate: '0.24',
    years: '10',
    annual_growth_rate: '0.05',
  },
};

export function template() {
  return html`
    <section class="page" id="tax-page">
      <div class="tax-shell" id="tax-shell">
        ${raw(masthead())}${skeleton('240px')}
      </div>
    </section>
  `;
}

export async function init() {
  attachHandlers();
  await load();
}

async function load() {
  const root = $('#tax-shell');
  if (!root) return;
  try {
    ui.harvest = await api.taxLossHarvest();
    ui.harvestError = null;
  } catch (err) {
    ui.harvest = null;
    ui.harvestError = err.message;
  }
  render();
}

function render() {
  const root = $('#tax-shell');
  if (!root) return;
  setView(root, html`
    ${raw(masthead())}
    ${raw(renderHarvestCard(ui.harvest, ui.harvestError))}
    ${raw(renderLadderCard())}
  `);
}

function masthead() {
  return html`
    <header class="settings-masthead">
      <div class="settings-masthead-text">
        <p class="settings-eyebrow">Strategy</p>
        <h1 class="settings-title">Tax strategy</h1>
        <p class="settings-lede">
          Harvesting candidates and conversion ladders from your own lots and brackets.
          Decision support — not advice, and nothing here executes a trade.
        </p>
      </div>
    </header>
  `.toString();
}

/* ─────────────  Tax-loss harvesting  ───────────── */

export function renderHarvestCard(report, error = null) {
  if (error) {
    return html`
      <section class="settings-card">
        <header class="settings-card-head">
          <div class="settings-card-kicker">Harvest</div>
          <h2 class="settings-card-title">Tax-loss harvesting</h2>
        </header>
        <p class="error-banner">${esc(error)}</p>
      </section>
    `.toString();
  }
  if (!report) return '';
  const candidates = Array.isArray(report.candidates) ? report.candidates : [];
  const lede = candidates.length
    ? `${candidates.length} lot${candidates.length === 1 ? '' : 's'} below basis in taxable accounts — `
      + `${fmtUsd(Math.abs(report.total_harvestable_loss_usd || 0))} harvestable, `
      + `≈${fmtUsd(report.total_estimated_tax_benefit_usd || 0)} estimated benefit.`
    : 'No taxable lots sit far enough below basis to harvest right now. Good problem to have.';
  return html`
    <section class="settings-card" id="tax-harvest">
      <header class="settings-card-head">
        <div class="settings-card-kicker">Harvest</div>
        <h2 class="settings-card-title">Tax-loss harvesting · as of ${esc(String(report.as_of || ''))}</h2>
        <p class="settings-card-lede">${esc(lede)}</p>
      </header>
      ${candidates.length ? html`
        <div class="benchmark-rows">
          ${raw(candidates.map(row => html`
            <div class="benchmark-row">
              <strong>${esc(String(row.symbol || ''))} · ${esc(String(row.term || ''))}-term</strong>
              <span>
                ${Number(row.quantity || 0).toLocaleString('en-US')} sh @ ${fmtUsd(row.unit_cost)} → ${fmtUsd(row.current_price)}
                ${row.wash_sale_risk ? ' · ⚠ wash-sale risk' : ''}
              </span>
              <span>${fmtUsd(row.unrealized_loss_usd)} · save ≈${fmtUsd(row.estimated_tax_benefit_usd)}</span>
            </div>
          `.toString()).join(''))}
        </div>
      ` : ''}
      <details class="diagnostics-toggle" style="margin-top: 12px;">
        <summary>How these numbers are estimated</summary>
        <ul class="settings-hint-list">
          ${raw((report.notes || []).map(note => `<li>${esc(String(note))}</li>`).join(''))}
        </ul>
      </details>
    </section>
  `.toString();
}

/* ─────────────  Roth conversion ladder  ───────────── */

const BRACKETS = [
  { value: '0.10', label: '10%' },
  { value: '0.12', label: '12%' },
  { value: '0.22', label: '22%' },
  { value: '0.24', label: '24%' },
  { value: '0.32', label: '32%' },
  { value: '0.35', label: '35%' },
];

function renderLadderCard() {
  const d = ui.draft;
  return html`
    <section class="settings-card" id="tax-ladder">
      <header class="settings-card-head">
        <div class="settings-card-kicker">Convert</div>
        <h2 class="settings-card-title">Roth conversion ladder</h2>
        <p class="settings-card-lede">
          Fill the target bracket each year; taxes are the full-engine delta including
          IRMAA. Filing status and state rate come from your profile.
        </p>
      </header>
      <div class="settings-grid">
        <label class="settings-field">
          <span class="settings-label">Traditional balance</span>
          <input id="tax-ladder-balance" class="settings-input mono" type="number" min="0" step="1000"
                 placeholder="e.g. 400000" value="${esc(d.traditional_balance_usd)}" />
        </label>
        <label class="settings-field">
          <span class="settings-label">Annual ordinary income</span>
          <input id="tax-ladder-income" class="settings-input mono" type="number" min="0" step="1000"
                 placeholder="defaults from profile" value="${esc(d.annual_ordinary_income_usd)}" />
        </label>
        <label class="settings-field">
          <span class="settings-label">Fill up to bracket</span>
          <select id="tax-ladder-bracket" class="settings-input">
            ${raw(BRACKETS.map(b => `
              <option value="${b.value}" ${b.value === d.target_bracket_rate ? 'selected' : ''}>${b.label}</option>`).join(''))}
          </select>
        </label>
        <label class="settings-field">
          <span class="settings-label">Years</span>
          <input id="tax-ladder-years" class="settings-input mono" type="number" min="1" max="30"
                 value="${esc(d.years)}" />
        </label>
        <label class="settings-field">
          <span class="settings-label">Growth assumption</span>
          <input id="tax-ladder-growth" class="settings-input mono" type="number" step="0.01" min="-0.5" max="0.5"
                 value="${esc(d.annual_growth_rate)}" />
        </label>
      </div>
      <footer class="settings-actions">
        <button class="btn btn-primary" id="tax-ladder-run" ${ui.ladderBusy ? 'disabled' : ''}>
          ${ui.ladderBusy ? 'Calculating…' : 'Build ladder'}
        </button>
      </footer>
      ${ui.ladderError ? html`<p class="error-banner">${esc(ui.ladderError)}</p>` : ''}
      ${raw(renderLadderResult(ui.ladder))}
    </section>
  `.toString();
}

export function renderLadderResult(result) {
  if (!result) return '';
  const rows = Array.isArray(result.schedule) ? result.schedule : [];
  if (!rows.length) return '<p class="settings-hint">No conversion room in the chosen window.</p>';
  const avg = result.average_rate_on_conversions;
  return html`
    <div id="tax-ladder-result">
      <p class="settings-card-lede" style="margin-top: 14px;">
        Converts ${fmtUsd(result.total_converted_usd)} over ${rows.length} year${rows.length === 1 ? '' : 's'}
        for ≈${fmtUsd(result.total_estimated_tax_usd)} in tax
        ${avg ? ` (${(avg * 100).toFixed(1)}% average on conversions)` : ''}.
        ${Number(result.remaining_balance_usd) > 0 ? ` ${fmtUsd(result.remaining_balance_usd)} remains unconverted.` : ''}
      </p>
      <div class="benchmark-rows">
        ${raw(rows.map(row => html`
          <div class="benchmark-row">
            <strong>${esc(String(row.year))}</strong>
            <span>convert ${fmtUsdOrDash(row.conversion_usd)} of ${fmtUsd(row.starting_balance_usd)}${row.note ? ` · ${esc(row.note)}` : ''}</span>
            <span>${fmtUsdOrDash(row.estimated_tax_usd)} tax${row.effective_rate_on_conversion ? ` · ${(row.effective_rate_on_conversion * 100).toFixed(1)}%` : ''}</span>
          </div>
        `.toString()).join(''))}
      </div>
      ${(result.warnings || []).length ? html`
        <div class="settings-hint" style="margin-top: 10px;">
          ${raw(result.warnings.map(w => `<p>⚠ ${esc(String(w))}</p>`).join(''))}
        </div>
      ` : ''}
    </div>
  `.toString();
}

/* ─────────────  events  ───────────── */

function attachHandlers() {
  const page = $('#tax-page');
  if (!page) return;
  page.addEventListener('input', event => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const map = {
      'tax-ladder-balance': 'traditional_balance_usd',
      'tax-ladder-income': 'annual_ordinary_income_usd',
      'tax-ladder-years': 'years',
      'tax-ladder-growth': 'annual_growth_rate',
    };
    const key = map[target.id];
    if (key) ui.draft[key] = target.value;
  });
  page.addEventListener('change', event => {
    const target = event.target;
    if (target instanceof HTMLSelectElement && target.id === 'tax-ladder-bracket') {
      ui.draft.target_bracket_rate = target.value;
    }
  });
  page.addEventListener('click', async event => {
    const target = event.target;
    if (!(target instanceof HTMLElement) || target.id !== 'tax-ladder-run') return;
    ui.ladderBusy = true;
    ui.ladderError = null;
    render();
    try {
      const d = ui.draft;
      ui.ladder = await api.rothLadder({
        traditional_balance_usd: Number(d.traditional_balance_usd) || 0,
        annual_ordinary_income_usd: d.annual_ordinary_income_usd === '' ? null : Number(d.annual_ordinary_income_usd),
        target_bracket_rate: Number(d.target_bracket_rate) || 0.24,
        years: Number(d.years) || 10,
        annual_growth_rate: Number(d.annual_growth_rate) || 0,
      });
    } catch (err) {
      ui.ladder = null;
      ui.ladderError = err.message;
    } finally {
      ui.ladderBusy = false;
      render();
    }
  });
}
