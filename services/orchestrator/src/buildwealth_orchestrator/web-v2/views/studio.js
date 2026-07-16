// THE STUDIO.
// The simulation engine on stage: move an assumption, watch a thousand
// futures redraw. Sliders re-run the full Monte Carlo engine live.

import { fetchJson } from '../lib/api.js';
import { html, raw, $, $$, esc } from '../lib/dom.js';
import { compactUsd } from '../lib/chart.js';
import { skeleton } from '../lib/skeleton.js';
import { heroFigure, terminalFigure, failureFigure, compositionFigure, scenarioStrip } from './studio/charts.js';

export const meta = {
  id: 'studio',
  label: 'Studio',
  numeral: 'IV',
  group: 'primary',
};

const RERUN_DEBOUNCE_MS = 420;
const SEED_MAX = 2_147_483_647;

// Slider definitions. `key` matches the ScenarioRequest field; null default
// means "engine default" until assumption-defaults resolve.
const CONTROLS = [
  { key: 'years', label: 'Horizon', min: 5, max: 60, step: 1, format: v => `${v} yrs` },
  { key: 'annual_contribution_usd', label: 'Annual contribution', min: 0, max: 150000, step: 2500, format: v => compactUsd(v) },
  { key: 'expected_return_baseline', label: 'Expected return', min: 0, max: 0.12, step: 0.0025, format: fmtPct },
  { key: 'return_volatility', label: 'Volatility', min: 0.04, max: 0.30, step: 0.005, format: fmtPct },
  { key: 'inflation_rate', label: 'Inflation', min: 0, max: 0.08, step: 0.0025, format: fmtPct },
];

const ui = {
  draft: {
    years: 30,
    annual_contribution_usd: 20000,
    expected_return_baseline: 0.06,
    return_volatility: 0.15,
    inflation_rate: 0.025,
    seed: 9521,
  },
  result: null,
  busy: false,
  error: null,
  loadedDefaults: false,
};

let debounceTimer = 0;
let runCounter = 0;

function fmtPct(value) {
  return `${(Number(value) * 100).toFixed(2).replace(/\.?0+$/, '')}%`;
}

export function template() {
  return html`
    <section class="page" id="studio-page">
      <header class="studio-masthead">
        <p class="studio-eyebrow">Movement ${meta.numeral} — Simulations</p>
        <h1 class="studio-title">The Studio.</h1>
        <p class="studio-lede">
          Every control below re-runs the full simulation engine — a thousand
          possible market histories against your actual accounts. Move a
          slider; watch your futures redraw.
        </p>
      </header>
      <div class="studio-layout">
        <aside class="studio-rail" id="studio-rail">${raw(renderRail())}</aside>
        <div class="studio-canvas" id="studio-canvas">
          ${skeleton('320px')}
          ${skeleton('200px', { marginTop: 'var(--s-4)' })}
        </div>
      </div>
    </section>
  `;
}

export async function init() {
  attachHandlers();
  if (!ui.loadedDefaults) await loadDefaults();
  renderRail(true);
  await run();
}

async function loadDefaults() {
  try {
    const payload = await fetchJson('/api/planning/assumption-defaults');
    const defaults = payload?.defaults || {};
    const pick = (key, fallback) => {
      const value = Number(defaults?.[key]?.value);
      return Number.isFinite(value) ? value : fallback;
    };
    ui.draft.years = clampControl('years', pick('years', ui.draft.years));
    ui.draft.annual_contribution_usd = clampControl(
      'annual_contribution_usd', pick('annual_contribution_usd', ui.draft.annual_contribution_usd));
    ui.draft.expected_return_baseline = clampControl(
      'expected_return_baseline', pick('expected_return_baseline', ui.draft.expected_return_baseline));
    ui.draft.inflation_rate = clampControl('inflation_rate', pick('inflation_rate', ui.draft.inflation_rate));
    ui.loadedDefaults = true;
  } catch {
    // Engine falls back to its own defaults; the sliders still work.
  }
}

function clampControl(key, value) {
  const control = CONTROLS.find(item => item.key === key);
  if (!control || !Number.isFinite(value)) return value;
  const stepped = Math.round((value - control.min) / control.step) * control.step + control.min;
  return Math.min(control.max, Math.max(control.min, Number(stepped.toFixed(6))));
}

async function run() {
  const runId = ++runCounter;
  ui.busy = true;
  ui.error = null;
  renderStatus();
  try {
    const result = await fetchJson('/api/planning/scenarios', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        years: ui.draft.years,
        annual_contribution_usd: ui.draft.annual_contribution_usd,
        expected_return_baseline: ui.draft.expected_return_baseline,
        return_volatility: ui.draft.return_volatility,
        inflation_rate: ui.draft.inflation_rate,
        simulation_mode: 'monte_carlo',
        simulation_seed: ui.draft.seed,
      }),
    });
    if (runId !== runCounter) return; // a newer slider move superseded this run
    ui.result = result;
  } catch (err) {
    if (runId !== runCounter) return;
    ui.error = err?.message || 'Simulation failed.';
  }
  ui.busy = false;
  renderCanvas();
  renderStatus();
}

function scheduleRun() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => { run(); }, RERUN_DEBOUNCE_MS);
}

/* ── Rendering ── */

function renderRail(commit = false) {
  const markup = html`
    <div class="studio-rail-card">
      <span class="studio-rail-eyebrow">Assumptions</span>
      ${raw(CONTROLS.map(renderControl).join(''))}
      <div class="studio-seed-row">
        <span class="studio-control-label">Market history</span>
        <span class="studio-seed-value" data-studio-seed>#${esc(String(ui.draft.seed))}</span>
        <button class="btn" type="button" data-studio-action="reroll">Deal another</button>
      </div>
      <p class="studio-status" id="studio-status" role="status"></p>
      <p class="marginalia">
        One seed is one deck of simulated market histories. Same seed, same
        deck — so slider moves compare like against like.
      </p>
    </div>
  `.toString();
  if (!commit) return markup;
  const rail = $('#studio-rail');
  if (rail) rail.innerHTML = markup;
  renderStatus();
  return markup;
}

function renderControl(control) {
  const value = ui.draft[control.key];
  return html`
    <label class="studio-control">
      <span class="studio-control-head">
        <span class="studio-control-label">${esc(control.label)}</span>
        <output class="studio-control-value" data-studio-value="${esc(control.key)}">${esc(control.format(value))}</output>
      </span>
      <input
        type="range"
        data-studio-control="${esc(control.key)}"
        min="${control.min}"
        max="${control.max}"
        step="${control.step}"
        value="${esc(String(value))}"
        aria-label="${esc(control.label)}"
      />
    </label>
  `.toString();
}

function renderStatus() {
  const status = $('#studio-status');
  if (!status) return;
  if (ui.busy) {
    status.textContent = 'Re-simulating…';
    status.className = 'studio-status is-busy';
  } else if (ui.error) {
    status.textContent = ui.error;
    status.className = 'studio-status is-error';
  } else {
    const runs = Number(ui.result?.monte_carlo?.runs);
    status.textContent = Number.isFinite(runs) && runs > 0
      ? `${runs.toLocaleString('en-US')} paths simulated.`
      : '';
    status.className = 'studio-status';
  }
}

function renderCanvas() {
  const canvas = $('#studio-canvas');
  if (!canvas) return;
  if (ui.error && !ui.result) {
    canvas.innerHTML = html`<p class="error-banner">${esc(ui.error)}</p>`;
    return;
  }
  if (!ui.result) return;
  canvas.innerHTML = html`
    ${raw(verdictStrip(ui.result))}
    ${raw(section('The paths', 'Each stroke is one simulated market history. The fan is where most of them land.', heroFigure(ui.result)))}
    ${raw(section('Where you end up', 'The full spread of ending balances across every simulation.', terminalFigure(ui.result)))}
    ${raw(section('When plans break', 'Among paths that ran short — the first year the money ran out.', failureFigure(ui.result)))}
    ${raw(section('Where the money sits', 'The same projection, split by how each dollar will be taxed.', compositionFigure(ui.result)))}
    ${raw(section('The four scenarios', 'The engine’s deterministic bookends around the simulation.', scenarioStrip(ui.result)))}
  `;
}

function section(title, lede, body) {
  if (!body) return '';
  return html`
    <section class="studio-section">
      <h2 class="studio-section-title">${esc(title)}</h2>
      <p class="studio-section-lede">${esc(lede)}</p>
      ${raw(body)}
    </section>
  `.toString();
}

function verdictStrip(result = {}) {
  const mc = result?.monte_carlo || {};
  const failure = mc.failure_analysis || {};
  const tiles = [
    { label: 'Plan strength', value: mc.plan_strength_label || '—', detail: Number.isFinite(Number(mc.plan_strength_score)) ? `${mc.plan_strength_score} / 100` : '' },
    { label: 'Paths funded', value: Number.isFinite(Number(mc.funded_trial_rate_pct)) ? `${mc.funded_trial_rate_pct}%` : '—', detail: fundedDetail(failure) },
    { label: 'Median outcome', value: compactUsd(mc.p50_future_value_usd), detail: `${compactUsd(mc.p50_real_value_usd)} in today’s dollars` },
    { label: 'The spread', value: `${compactUsd(mc.p10_future_value_usd)} – ${compactUsd(mc.p90_future_value_usd)}`, detail: '10th to 90th percentile' },
  ];
  return html`
    <div class="studio-verdict">
      ${raw(tiles.map(tile => html`
        <div class="studio-verdict-tile">
          <span class="studio-verdict-label">${esc(tile.label)}</span>
          <span class="studio-verdict-value">${esc(tile.value)}</span>
          <span class="studio-verdict-detail">${esc(tile.detail)}</span>
        </div>
      `.toString()).join(''))}
    </div>
  `.toString();
}

function fundedDetail(failure = {}) {
  const failed = Number(failure.failed_trial_count);
  if (!Number.isFinite(failed) || failed <= 0) return 'no paths ran short';
  const median = failure.first_failure_year_median;
  return median ? `${failed.toLocaleString('en-US')} ran short · median first shortfall ${median}` : `${failed.toLocaleString('en-US')} ran short`;
}

/* ── Events ── */

let handlersWired = false;

function attachHandlers() {
  if (handlersWired) return;
  handlersWired = true;

  document.addEventListener('input', event => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || !input.matches('[data-studio-control]')) return;
    const key = input.getAttribute('data-studio-control');
    const control = CONTROLS.find(item => item.key === key);
    if (!control) return;
    const value = Number(input.value);
    if (!Number.isFinite(value)) return;
    ui.draft[key] = value;
    const output = $(`[data-studio-value="${key}"]`);
    if (output) output.textContent = control.format(value);
    scheduleRun();
  });

  document.addEventListener('click', event => {
    const button = event.target instanceof Element
      ? event.target.closest('[data-studio-action="reroll"]')
      : null;
    if (!button) return;
    ui.draft.seed = Math.floor(Math.random() * SEED_MAX);
    const seedLabel = $('[data-studio-seed]');
    if (seedLabel) seedLabel.textContent = `#${ui.draft.seed}`;
    scheduleRun();
  });
}
