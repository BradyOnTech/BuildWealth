// THE STUDIO — visual forecast theater.
// Present → plan forecast → stress → life-lever experiments → depth charts.
// Language stays plain: no bare p10/p90/volatility for non-experts.

import { api, fetchJson } from '../lib/api.js';
import { html, raw, $, esc } from '../lib/dom.js';
import { compactUsd } from '../lib/chart.js';
import { skeleton } from '../lib/skeleton.js';
import { heroFigure, terminalFigure, failureFigure, compositionFigure, scenarioStrip } from './studio/charts.js';
import {
  strengthHeadline,
  strengthExplain,
  fundedPhrase,
  spreadPhrase,
  medianPhrase,
  formatPct,
  formatReturnPct,
  formatMoneyPerYear,
  formatYears,
  formatExpenseScale,
  deltaMoney,
  deltaPoints,
  GLOSSARY,
  CONTROL_HELP,
  trajectoryStatusPhrase,
  failureSentence,
  improvementChips,
  changedLevers,
  isDirty,
} from './studio/language.js';

export const meta = {
  id: 'studio',
  label: 'Studio',
  numeral: 'IV',
  group: 'primary',
};

const RERUN_DEBOUNCE_MS = 420;
const SEED_MAX = 2_147_483_647;

const LIFE_CONTROLS = [
  {
    key: 'annual_contribution_usd',
    label: 'Yearly saving',
    min: 0,
    max: 150000,
    step: 2500,
    format: formatMoneyPerYear,
  },
  {
    key: 'target_retirement_age',
    label: 'Retire around',
    min: 40,
    max: 80,
    step: 1,
    format: v => `age ${Math.round(Number(v))}`,
  },
  {
    key: 'expense_scale',
    label: 'Spending level',
    min: 0.5,
    max: 1.5,
    step: 0.05,
    format: formatExpenseScale,
  },
  {
    key: 'years',
    label: 'Years ahead to show',
    min: 5,
    max: 80,
    step: 1,
    format: formatYears,
  },
];

const ADVANCED_CONTROLS = [
  {
    key: 'expected_return_baseline',
    label: 'Expected yearly growth',
    min: 0,
    max: 0.12,
    step: 0.0025,
    format: formatReturnPct,
  },
  {
    key: 'return_volatility',
    label: 'Market ups and downs',
    min: 0.04,
    max: 0.30,
    step: 0.005,
    format: formatReturnPct,
  },
  {
    key: 'inflation_rate',
    label: 'Inflation',
    min: 0,
    max: 0.08,
    step: 0.0025,
    format: formatReturnPct,
  },
];

const DEFAULT_DRAFT = {
  years: 30,
  annual_contribution_usd: 20000,
  expected_return_baseline: 0.06,
  return_volatility: 0.15,
  inflation_rate: 0.025,
  target_retirement_age: 65,
  expense_scale: 1,
  simulation_mode: 'monte_carlo',
  simulation_historical_start_year: 2000,
  seed: 9521,
};

const ui = {
  context: {
    planId: '',
    planTitle: '',
    portfolioValue: null,
    tracking: null,
    age: null,
    timelineEvents: [],
    peer: null,
    warnings: [],
  },
  baseline: { ...DEFAULT_DRAFT },
  draft: { ...DEFAULT_DRAFT },
  baselineResult: null,
  result: null,
  dollarsMode: 'real',
  showAdvanced: false,
  depthOpen: { terminal: false, composition: false, scenarios: false },
  busy: false,
  baselineBusy: false,
  error: null,
  saveBusy: false,
  saveMessage: null,
  saveError: null,
  loaded: false,
};

let debounceTimer = 0;
let runCounter = 0;
let handlersWired = false;

export function template() {
  return html`
    <section class="page" id="studio-page">
      <header class="studio-masthead">
        <p class="studio-eyebrow">Movement ${meta.numeral} — Your money story</p>
        <h1 class="studio-title">The Studio.</h1>
        <p class="studio-lede">
          See where you are, how your plan holds up across many possible markets,
          and what changes if you save more, retire later, or spend differently.
          Nothing here changes your real plan until you choose to save an experiment.
        </p>
      </header>
      <div class="studio-layout">
        <aside class="studio-rail" id="studio-rail">${skeleton('280px')}</aside>
        <div class="studio-canvas" id="studio-canvas">
          ${skeleton('120px')}
          ${skeleton('320px', { marginTop: 'var(--s-4)' })}
          ${skeleton('200px', { marginTop: 'var(--s-4)' })}
        </div>
      </div>
      <div class="studio-sticky-verdict" id="studio-sticky-verdict" hidden></div>
    </section>
  `;
}

export async function init() {
  attachHandlers();
  await loadContext();
  renderRail(true);
  renderCanvas();
  await runBaselineAndCandidate();
}

/* ── Context loading ── */

async function loadContext() {
  const warnings = [];
  let planId = '';
  let planTitle = '';
  let portfolioValue = null;
  let tracking = null;
  let age = null;
  let timelineEvents = [];
  let peer = null;
  let defaults = {};
  let planSettings = {};
  let retirementAge = DEFAULT_DRAFT.target_retirement_age;

  try {
    const payload = await api.planningAssumptionDefaults();
    defaults = payload?.defaults || {};
  } catch {
    warnings.push('Could not load default planning numbers — using built-in starting points.');
  }

  try {
    const plans = await api.plans(50);
    const list = Array.isArray(plans?.plans) ? plans.plans : Array.isArray(plans) ? plans : [];
    const active = list.find(p => p?.is_active) || list[0];
    if (active?.id) {
      planId = String(active.id);
      planTitle = String(active.title || 'Your plan');
      try {
        const plan = await api.plan(planId);
        planSettings = plan?.settings && typeof plan.settings === 'object' ? plan.settings : {};
        planTitle = String(plan?.title || planTitle);
        try {
          const sets = await api.planAssumptionSets(planId);
          const activeId = String(sets?.active_assumption_set_id || '').trim();
          const activeSet = Array.isArray(sets?.sets)
            ? sets.sets.find(s => String(s?.id || '') === activeId)
            : null;
          if (activeSet && typeof activeSet === 'object') {
            for (const [key, value] of Object.entries(activeSet)) {
              if (key === 'id' || key === 'name' || value == null) continue;
              planSettings[key] = value;
            }
          }
        } catch { /* assumption sets optional */ }
        try {
          const timeline = await api.planTimeline(planId);
          const retirement = timeline?.retirement || timeline?.timeline?.retirement || {};
          if (retirement?.target_retirement_age != null) {
            retirementAge = Number(retirement.target_retirement_age);
          }
          const events = timeline?.events || timeline?.timeline?.events || [];
          timelineEvents = Array.isArray(events) ? events : [];
        } catch { /* timeline optional */ }
        try {
          tracking = await api.planTracking(planId);
        } catch { /* tracking optional */ }
      } catch {
        warnings.push('Could not open your active plan — starting from shared defaults.');
      }
    } else {
      warnings.push('No plan yet — set one up in Plan for a tighter forecast.');
    }
  } catch {
    warnings.push('Could not load plans.');
  }

  try {
    const holdings = await api.holdings();
    const total = Number(holdings?.total_value ?? holdings?.total_portfolio_value);
    if (Number.isFinite(total) && total > 0) portfolioValue = total;
    else if (Number(holdings?.total_cash) > 0) portfolioValue = Number(holdings.total_cash);
  } catch {
    warnings.push('Portfolio value unavailable — forecast may use a placeholder start.');
  }

  try {
    peer = await api.peerBenchmark();
    if (peer?.status !== 'ready') peer = null;
  } catch {
    peer = null;
  }

  const pick = (key, fallback) => {
    const fromPlan = Number(planSettings?.[key]);
    if (Number.isFinite(fromPlan)) return fromPlan;
    const fromDefault = Number(defaults?.[key]?.value);
    if (Number.isFinite(fromDefault)) return fromDefault;
    return fallback;
  };

  const baseline = {
    years: clampControl('years', pick('years', DEFAULT_DRAFT.years)),
    annual_contribution_usd: clampControl(
      'annual_contribution_usd',
      pick('annual_contribution_usd', DEFAULT_DRAFT.annual_contribution_usd),
    ),
    expected_return_baseline: clampControl(
      'expected_return_baseline',
      pick('expected_return_baseline', DEFAULT_DRAFT.expected_return_baseline),
    ),
    return_volatility: clampControl(
      'return_volatility',
      pick('return_volatility', DEFAULT_DRAFT.return_volatility),
    ),
    inflation_rate: clampControl(
      'inflation_rate',
      pick('inflation_rate', DEFAULT_DRAFT.inflation_rate),
    ),
    target_retirement_age: clampRange(
      retirementAge,
      LIFE_CONTROLS.find(c => c.key === 'target_retirement_age'),
    ),
    expense_scale: 1,
    simulation_mode: 'monte_carlo',
    simulation_historical_start_year: 2000,
    seed: Number.isFinite(Number(planSettings.simulation_seed))
      ? Number(planSettings.simulation_seed)
      : DEFAULT_DRAFT.seed,
  };

  if (!Number.isFinite(Number(planSettings.return_volatility))
    && !Number.isFinite(Number(defaults?.return_volatility?.value))) {
    // keep DEFAULT volatility
  }

  ui.baseline = baseline;
  ui.draft = { ...baseline };
  ui.context = {
    planId,
    planTitle,
    portfolioValue,
    tracking,
    age,
    timelineEvents,
    peer,
    warnings,
  };
  ui.loaded = true;
}

function clampControl(key, value) {
  const control = [...LIFE_CONTROLS, ...ADVANCED_CONTROLS].find(item => item.key === key);
  return clampRange(value, control);
}

function clampRange(value, control) {
  if (!control || !Number.isFinite(Number(value))) return value;
  const n = Number(value);
  const stepped = Math.round((n - control.min) / control.step) * control.step + control.min;
  return Math.min(control.max, Math.max(control.min, Number(stepped.toFixed(6))));
}

/* ── Simulation runs ── */

function requestBody(from = ui.draft) {
  const body = {
    years: from.years,
    annual_contribution_usd: from.annual_contribution_usd,
    expected_return_baseline: from.expected_return_baseline,
    return_volatility: from.return_volatility,
    inflation_rate: from.inflation_rate,
    target_retirement_age: from.target_retirement_age,
    expense_scale: from.expense_scale,
    simulation_mode: from.simulation_mode || 'monte_carlo',
    simulation_seed: from.seed,
  };
  if (body.simulation_mode === 'historical') {
    body.simulation_historical_start_year = from.simulation_historical_start_year || 2000;
  }
  if (Number.isFinite(Number(ui.context.portfolioValue))) {
    body.current_portfolio_value_usd = Number(ui.context.portfolioValue);
  }
  return body;
}

async function runBaselineAndCandidate() {
  ui.baselineBusy = true;
  ui.busy = true;
  ui.error = null;
  renderRail(true);
  renderStatus();
  const runId = ++runCounter;
  try {
    const baselineBody = requestBody(ui.baseline);
    baselineBody.simulation_mode = 'monte_carlo';
    const baselineResult = await fetchJson('/api/planning/scenarios', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(baselineBody),
    });
    if (runId !== runCounter) return;
    ui.baselineResult = baselineResult;

    if (!isDirty(ui.draft, ui.baseline) && ui.draft.simulation_mode === 'monte_carlo') {
      ui.result = baselineResult;
    } else {
      const candidate = await fetchJson('/api/planning/scenarios', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(requestBody(ui.draft)),
      });
      if (runId !== runCounter) return;
      ui.result = candidate;
    }
  } catch (err) {
    if (runId !== runCounter) return;
    ui.error = err?.message || 'Simulation failed.';
  }
  ui.baselineBusy = false;
  ui.busy = false;
  renderRail(true);
  renderCanvas();
  renderStatus();
  renderSticky();
}

async function runCandidate() {
  const runId = ++runCounter;
  ui.busy = true;
  ui.error = null;
  ui.saveMessage = null;
  renderStatus();
  renderSticky();
  try {
    // Same settings as plan + Monte Carlo: reuse baseline result (no double work).
    if (!isDirty(ui.draft, ui.baseline) && ui.draft.simulation_mode === 'monte_carlo' && ui.baselineResult) {
      if (runId !== runCounter) return;
      ui.result = ui.baselineResult;
    } else {
      const result = await fetchJson('/api/planning/scenarios', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(requestBody(ui.draft)),
      });
      if (runId !== runCounter) return;
      ui.result = result;
    }
  } catch (err) {
    if (runId !== runCounter) return;
    ui.error = err?.message || 'Simulation failed.';
  }
  ui.busy = false;
  renderCanvas();
  renderStatus();
  renderSticky();
}

function scheduleRun() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => { runCandidate(); }, RERUN_DEBOUNCE_MS);
}

/* ── Rail ── */

function renderRail(commit = false) {
  const dirty = isDirty(ui.draft, ui.baseline) || ui.draft.simulation_mode !== 'monte_carlo';
  const mode = ui.draft.simulation_mode || 'monte_carlo';
  const markup = html`
    <div class="studio-rail-card">
      <span class="studio-rail-eyebrow">Try a change</span>
      <p class="studio-rail-intro">
        Move a control to experiment. Your real plan stays put until you save.
      </p>

      <div class="studio-mode-row" role="group" aria-label="Forecast style">
        <button
          type="button"
          class="studio-mode-btn ${mode === 'monte_carlo' ? 'is-active' : ''}"
          data-studio-mode="monte_carlo"
        >Many markets</button>
        <button
          type="button"
          class="studio-mode-btn ${mode === 'historical' ? 'is-active' : ''}"
          data-studio-mode="historical"
        >One past stretch</button>
      </div>
      <p class="studio-control-help">
        ${mode === 'historical'
          ? 'Replays one stretch of real past markets on your plan.'
          : 'Tests thousands of possible market ups and downs.'}
      </p>

      ${mode === 'historical' ? raw(renderHistoricalYear()) : ''}

      ${raw(LIFE_CONTROLS.map(renderControl).join(''))}

      <details class="studio-advanced" ${ui.showAdvanced ? 'open' : ''}>
        <summary>Advanced market assumptions</summary>
        <p class="studio-control-help">
          Only change these if you understand growth, inflation, and risk. Defaults come from your plan.
        </p>
        ${raw(ADVANCED_CONTROLS.map(renderControl).join(''))}
        <div class="studio-seed-row">
          <span class="studio-control-label">Same market deck</span>
          <span class="studio-seed-value" data-studio-seed>#${esc(String(ui.draft.seed))}</span>
          <button class="btn" type="button" data-studio-action="reroll">Shuffle deck</button>
        </div>
        <p class="studio-control-help">${esc(GLOSSARY.seed.body)}</p>
      </details>

      <div class="studio-rail-actions">
        <button class="btn" type="button" data-studio-action="reset" ${dirty ? '' : 'disabled'}>
          Back to my plan
        </button>
        ${ui.context.planId ? html`
          <button
            class="btn btn-primary"
            type="button"
            data-studio-action="save"
            ${ui.saveBusy || ui.busy || !ui.result ? 'disabled' : ''}
          >
            ${ui.saveBusy ? 'Saving…' : 'Save this experiment'}
          </button>
        ` : ''}
      </div>

      ${ui.context.planId ? html`
        <p class="studio-control-help">
          Saving keeps an immutable snapshot under
          <a class="link-editorial" href="#plan?id=${esc(ui.context.planId)}&amp;section=scenarios">Plan → Simulations</a>.
          It does not change the active plan.
        </p>
      ` : html`
        <p class="studio-control-help">
          <a class="link-editorial" href="#plan">Create a plan</a> to save experiments as evidence.
        </p>
      `}

      <p class="studio-status" id="studio-status" role="status"></p>
      ${ui.saveMessage ? html`<p class="studio-save-ok">${esc(ui.saveMessage)}</p>` : ''}
      ${ui.saveError ? html`<p class="studio-save-err">${esc(ui.saveError)}</p>` : ''}
    </div>
  `.toString();

  if (!commit) return markup;
  const rail = $('#studio-rail');
  if (rail) rail.innerHTML = markup;
  renderStatus();
  return markup;
}

function renderHistoricalYear() {
  const year = ui.draft.simulation_historical_start_year || 2000;
  return html`
    <label class="studio-control">
      <span class="studio-control-head">
        <span class="studio-control-label">History starts in</span>
        <output class="studio-control-value">${esc(String(year))}</output>
      </span>
      <input
        type="range"
        data-studio-control="simulation_historical_start_year"
        min="1928"
        max="2015"
        step="1"
        value="${esc(String(year))}"
        aria-label="Historical start year"
      />
      <span class="studio-control-help">${esc(CONTROL_HELP.simulation_historical_start_year)}</span>
    </label>
  `.toString();
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
      <span class="studio-control-help">${esc(CONTROL_HELP[control.key] || '')}</span>
    </label>
  `.toString();
}

function renderStatus() {
  const status = $('#studio-status');
  if (!status) return;
  if (ui.busy || ui.baselineBusy) {
    status.textContent = ui.baselineBusy ? 'Building your plan picture…' : 'Updating your experiment…';
    status.className = 'studio-status is-busy';
  } else if (ui.error) {
    status.textContent = ui.error;
    status.className = 'studio-status is-error';
  } else {
    const runs = Number(ui.result?.monte_carlo?.runs);
    status.textContent = Number.isFinite(runs) && runs > 0
      ? `${runs.toLocaleString('en-US')} market histories compared.`
      : ui.result ? 'Forecast ready.' : '';
    status.className = 'studio-status';
  }
}

/* ── Canvas ── */

function renderCanvas() {
  const canvas = $('#studio-canvas');
  if (!canvas) return;
  if (ui.error && !ui.result && !ui.baselineResult) {
    canvas.innerHTML = html`<p class="error-banner">${esc(ui.error)}</p>`;
    return;
  }

  const result = ui.result || ui.baselineResult;
  const dirty = isDirty(ui.draft, ui.baseline) || ui.draft.simulation_mode !== 'monte_carlo';
  // When dirty, overlay candidate on plan baseline; when clean, no dashed twin.
  const baselineForChart = dirty ? ui.baselineResult : null;

  canvas.innerHTML = html`
    ${raw(presentStrip())}
    ${raw(toolbar())}
    <div class="studio-canvas-body ${ui.busy ? 'is-redrawing' : ''}">
      ${result ? raw(verdictStrip(result, dirty ? ui.baselineResult : null)) : skeleton('100px')}
      ${result ? raw(summarySentence(result)) : ''}
      ${dirty ? raw(changesStrip()) : ''}
      ${result ? raw(chipsRow(result)) : ''}
      ${raw(section(
        'How your money could grow',
        'Each path is one possible market future. The shaded band is where most histories land. The solid line is the middle outcome.',
        result
          ? heroFigure(result, baselineForChart, {
            dollarsMode: ui.dollarsMode,
            peer: ui.context.peer,
            timelineEvents: ui.context.timelineEvents,
          })
          : '',
        { glossary: ['market_histories', 'middle_outcome', 'your_plan', ui.dollarsMode === 'real' ? 'todays_dollars' : 'future_dollars'] },
      ))}
      ${result ? raw(section(
        'When money might run short',
        failureSentence(result?.monte_carlo?.failure_analysis, result?.monte_carlo?.runs),
        failureFigure(result),
        { glossary: ['when_plans_break'], always: true },
      )) : ''}
      ${result ? raw(depthSections(result)) : ''}
    </div>
  `;
  renderSticky();
}

function presentStrip() {
  const { portfolioValue, planTitle, planId, tracking, warnings } = ui.context;
  const b = ui.baseline;
  const track = trajectoryStatusPhrase(tracking);
  const parts = [];
  if (Number.isFinite(Number(portfolioValue))) {
    parts.push(`Starting from <strong>${esc(compactUsd(portfolioValue))}</strong> invested`);
  }
  parts.push(`saving about <strong>${esc(formatMoneyPerYear(b.annual_contribution_usd))}</strong>`);
  parts.push(`retiring around <strong>age ${esc(String(Math.round(b.target_retirement_age)))}</strong>`);
  parts.push(`looking <strong>${esc(formatYears(b.years))}</strong> ahead`);

  return html`
    <section class="studio-present">
      <div class="studio-present-main">
        <span class="studio-rail-eyebrow">Where you are</span>
        <p class="studio-present-line">
          ${raw(parts.join(' · '))}
        </p>
        <p class="studio-present-plan">
          ${planId
            ? html`Baseline: <a class="link-editorial" href="#plan?id=${esc(planId)}">${esc(planTitle || 'Your plan')}</a>`
            : html`Baseline: shared defaults · <a class="link-editorial" href="#plan">set up a plan</a>`}
          ${track ? html` · ${esc(track)}` : ''}
        </p>
      </div>
      ${warnings?.length ? html`
        <ul class="studio-warnings">
          ${raw(warnings.map(w => html`<li>${esc(w)}</li>`).join(''))}
        </ul>
      ` : ''}
    </section>
  `.toString();
}

function toolbar() {
  return html`
    <div class="studio-toolbar">
      <div class="studio-toggle" role="group" aria-label="Dollar units">
        <button
          type="button"
          class="studio-mode-btn ${ui.dollarsMode === 'real' ? 'is-active' : ''}"
          data-studio-dollars="real"
        >Today’s dollars</button>
        <button
          type="button"
          class="studio-mode-btn ${ui.dollarsMode === 'nominal' ? 'is-active' : ''}"
          data-studio-dollars="nominal"
        >Future dollars</button>
      </div>
      <p class="studio-control-help studio-toolbar-help">
        ${ui.dollarsMode === 'real'
          ? esc(GLOSSARY.todays_dollars.body)
          : esc(GLOSSARY.future_dollars.body)}
      </p>
    </div>
  `.toString();
}

function verdictStrip(result = {}, baselineResult = null) {
  const mc = result?.monte_carlo || {};
  const baseMc = baselineResult?.monte_carlo || {};
  const useReal = ui.dollarsMode === 'real';
  const median = useReal ? mc.p50_real_value_usd : mc.p50_future_value_usd;
  const lo = useReal ? mc.p10_real_value_usd : mc.p10_future_value_usd;
  const hi = useReal ? mc.p90_real_value_usd : mc.p90_future_value_usd;
  const baseMedian = useReal ? baseMc.p50_real_value_usd : baseMc.p50_future_value_usd;
  const fundedDelta = baselineResult ? deltaPoints(mc.funded_trial_rate_pct, baseMc.funded_trial_rate_pct) : null;
  const medianDelta = baselineResult ? deltaMoney(median, baseMedian) : null;
  const strengthDelta = baselineResult && baseMc.plan_strength_label && mc.plan_strength_label
    && baseMc.plan_strength_label !== mc.plan_strength_label
    ? `${strengthHeadline(baseMc.plan_strength_label)} → ${strengthHeadline(mc.plan_strength_label)}`
    : '';

  const tiles = [
    {
      label: 'Plan strength',
      value: strengthHeadline(mc.plan_strength_label),
      detail: strengthDelta || (Number.isFinite(Number(mc.plan_strength_score))
        ? `${formatPct(mc.plan_strength_score)} of histories lasted`
        : strengthExplain(mc.plan_strength_label)),
      tip: GLOSSARY.plan_strength.body,
    },
    {
      label: 'Money lasted',
      value: Number.isFinite(Number(mc.funded_trial_rate_pct)) ? formatPct(mc.funded_trial_rate_pct) : '—',
      detail: fundedDelta
        ? `${fundedDelta.text} vs your plan`
        : fundedPhrase(mc.funded_trial_rate_pct),
      tip: GLOSSARY.market_histories.body,
    },
    {
      label: 'Middle outcome',
      value: compactUsd(median),
      detail: medianDelta
        ? `${medianDelta.text} vs your plan`
        : medianPhrase(median, { real: useReal }),
      tip: GLOSSARY.middle_outcome.body,
    },
    {
      label: 'Tougher → better',
      value: `${compactUsd(lo)} – ${compactUsd(hi)}`,
      detail: spreadPhrase(lo, hi, { real: useReal }),
      tip: GLOSSARY.tough_good_range.body,
    },
  ];

  return html`
    <div class="studio-verdict">
      ${raw(tiles.map(tile => html`
        <div class="studio-verdict-tile" title="${esc(tile.tip || '')}">
          <span class="studio-verdict-label">${esc(tile.label)}</span>
          <span class="studio-verdict-value">${esc(tile.value)}</span>
          <span class="studio-verdict-detail">${esc(tile.detail)}</span>
        </div>
      `.toString()).join(''))}
    </div>
  `.toString();
}

function summarySentence(result = {}) {
  const mc = result?.monte_carlo || {};
  const summary = String(mc.plan_strength_summary || '').trim();
  const headline = strengthHeadline(mc.plan_strength_label);
  const explain = strengthExplain(mc.plan_strength_label);
  return html`
    <p class="studio-summary">
      <strong>${esc(headline)}.</strong>
      ${esc(summary || explain)}
    </p>
  `.toString();
}

function changesStrip() {
  const changes = changedLevers(ui.draft, ui.baseline);
  if (!changes.length && ui.draft.simulation_mode === 'historical') {
    return html`
      <p class="studio-changes">
        Experiment: replaying markets from <strong>${esc(String(ui.draft.simulation_historical_start_year))}</strong>
        instead of many random futures.
      </p>
    `.toString();
  }
  if (!changes.length) return '';
  return html`
    <p class="studio-changes">
      You changed
      ${raw(changes.map((c, i) => html`
        ${i ? ', ' : ''}
        <strong>${esc(c.label)}</strong> (${esc(c.from)} → ${esc(c.to)})
      `.toString()).join(''))}.
      Dashed line on the chart is your unchanged plan.
    </p>
  `.toString();
}

function chipsRow(result = {}) {
  const chips = improvementChips({
    draft: ui.draft,
    baseline: ui.baseline,
    result,
    context: ui.context,
  });
  if (!chips.length) return '';
  return html`
    <div class="studio-chips">
      <span class="studio-chips-label">Try this</span>
      ${raw(chips.map(chip => html`
        <button
          type="button"
          class="studio-chip"
          data-studio-chip="${esc(chip.id)}"
          title="${esc(chip.detail)}"
        >${esc(chip.label)}</button>
      `.toString()).join(''))}
    </div>
  `.toString();
}

function depthSections(result = {}) {
  const hasMc = result?.monte_carlo && Array.isArray(result.monte_carlo.percentile_timeline)
    && result.monte_carlo.percentile_timeline.length > 1;
  return html`
    <details class="studio-depth" ${ui.depthOpen.terminal ? 'open' : ''} data-studio-depth="terminal">
      <summary>
        <span class="studio-depth-title">Where you might end up</span>
        <span class="studio-depth-lede">A simple histogram of ending balances across all market histories</span>
      </summary>
      ${hasMc ? raw(terminalFigure(result, { dollarsMode: ui.dollarsMode })) : html`
        <p class="studio-section-note">Available when using “Many markets.”</p>
      `}
    </details>
    <div class="studio-depth-grid">
      <details class="studio-depth" ${ui.depthOpen.composition ? 'open' : ''} data-studio-depth="composition">
        <summary>
          <span class="studio-depth-title">Where the money sits</span>
          <span class="studio-depth-lede">Taxable vs tax-deferred vs tax-free over time</span>
        </summary>
        ${raw(compositionFigure(result))}
      </details>
      <details class="studio-depth" ${ui.depthOpen.scenarios ? 'open' : ''} data-studio-depth="scenarios">
        <summary>
          <span class="studio-depth-title">Four simple bookends</span>
          <span class="studio-depth-lede">Steady, stronger, weaker, and extra HSA paths</span>
        </summary>
        ${raw(scenarioStrip(result))}
      </details>
    </div>
    ${raw(glossaryPanel())}
  `.toString();
}

function glossaryPanel() {
  const keys = ['plan_strength', 'market_histories', 'middle_outcome', 'tough_good_range', 'todays_dollars', 'when_plans_break'];
  return html`
    <details class="studio-glossary">
      <summary>What do these words mean?</summary>
      <dl class="studio-glossary-list">
        ${raw(keys.map(key => {
          const entry = GLOSSARY[key];
          if (!entry) return '';
          return html`
            <div>
              <dt>${esc(entry.title)}</dt>
              <dd>${esc(entry.body)}</dd>
            </div>
          `.toString();
        }).join(''))}
      </dl>
    </details>
  `.toString();
}

function section(title, lede, body, { glossary = [], always = false } = {}) {
  if (!body && !always) return '';
  return html`
    <section class="studio-section">
      <h2 class="studio-section-title">${esc(title)}</h2>
      <p class="studio-section-lede">${esc(lede)}</p>
      ${glossary.length ? html`
        <p class="studio-section-note">
          ${raw(glossary.map((key, i) => {
            const g = GLOSSARY[key];
            if (!g) return '';
            return html`${i ? ' · ' : ''}<abbr title="${esc(g.body)}">${esc(g.title)}</abbr>`;
          }).join(''))}
        </p>
      ` : ''}
      ${raw(body || '')}
    </section>
  `.toString();
}

function renderSticky() {
  const el = $('#studio-sticky-verdict');
  if (!el) return;
  const result = ui.result || ui.baselineResult;
  if (!result?.monte_carlo) {
    el.hidden = true;
    return;
  }
  const mc = result.monte_carlo;
  const base = ui.baselineResult?.monte_carlo;
  const dirty = isDirty(ui.draft, ui.baseline);
  const useReal = ui.dollarsMode === 'real';
  const median = useReal ? mc.p50_real_value_usd : mc.p50_future_value_usd;
  const delta = dirty && base
    ? deltaPoints(mc.funded_trial_rate_pct, base.funded_trial_rate_pct)
    : null;
  el.hidden = false;
  el.innerHTML = html`
    <span><strong>${esc(strengthHeadline(mc.plan_strength_label))}</strong></span>
    <span>${esc(formatPct(mc.funded_trial_rate_pct))} lasted</span>
    <span>Middle ${esc(compactUsd(median))}</span>
    ${delta && delta.dir !== 'flat' ? html`<span class="studio-sticky-delta ${delta.dir}">${esc(delta.text)} vs plan</span>` : ''}
    ${ui.busy ? html`<span class="studio-sticky-busy">Updating…</span>` : ''}
  `.toString();
}

/* ── Events ── */

function attachHandlers() {
  if (handlersWired) return;
  handlersWired = true;

  document.addEventListener('input', event => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || !input.matches('[data-studio-control]')) return;
    const key = input.getAttribute('data-studio-control');
    const control = [...LIFE_CONTROLS, ...ADVANCED_CONTROLS].find(item => item.key === key);
    const value = Number(input.value);
    if (!Number.isFinite(value)) return;
    if (key === 'simulation_historical_start_year') {
      ui.draft.simulation_historical_start_year = Math.round(value);
      const output = input.closest('.studio-control')?.querySelector('.studio-control-value');
      if (output) output.textContent = String(Math.round(value));
      scheduleRun();
      return;
    }
    if (!control) return;
    ui.draft[key] = value;
    const output = $(`[data-studio-value="${key}"]`);
    if (output) output.textContent = control.format(value);
    scheduleRun();
  });

  document.addEventListener('click', event => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;

    const modeBtn = target.closest('[data-studio-mode]');
    if (modeBtn) {
      const mode = modeBtn.getAttribute('data-studio-mode');
      if (mode === 'monte_carlo' || mode === 'historical') {
        ui.draft.simulation_mode = mode;
        renderRail(true);
        scheduleRun();
      }
      return;
    }

    const dollarsBtn = target.closest('[data-studio-dollars]');
    if (dollarsBtn) {
      const mode = dollarsBtn.getAttribute('data-studio-dollars');
      if (mode === 'real' || mode === 'nominal') {
        ui.dollarsMode = mode;
        renderCanvas();
      }
      return;
    }

    const chip = target.closest('[data-studio-chip]');
    if (chip) {
      const id = chip.getAttribute('data-studio-chip');
      const chips = improvementChips({
        draft: ui.draft,
        baseline: ui.baseline,
        result: ui.result || ui.baselineResult,
        context: ui.context,
      });
      const match = chips.find(c => c.id === id);
      if (match?.patch) {
        Object.assign(ui.draft, match.patch);
        // clamp patched life controls
        for (const key of Object.keys(match.patch)) {
          const control = [...LIFE_CONTROLS, ...ADVANCED_CONTROLS].find(c => c.key === key);
          if (control) ui.draft[key] = clampRange(ui.draft[key], control);
        }
        renderRail(true);
        scheduleRun();
      }
      return;
    }

    const action = target.closest('[data-studio-action]');
    if (!action) {
      // track depth open state
      const depth = target.closest('[data-studio-depth]');
      if (depth instanceof HTMLDetailsElement) {
        // let toggle settle
        setTimeout(() => {
          const key = depth.getAttribute('data-studio-depth');
          if (key && key in ui.depthOpen) ui.depthOpen[key] = depth.open;
        }, 0);
      }
      return;
    }

    const name = action.getAttribute('data-studio-action');
    if (name === 'reroll') {
      ui.draft.seed = Math.floor(Math.random() * SEED_MAX);
      // Baseline should share the same deck so compare stays fair.
      ui.baseline.seed = ui.draft.seed;
      const seedLabel = $('[data-studio-seed]');
      if (seedLabel) seedLabel.textContent = `#${ui.draft.seed}`;
      // Need fresh baseline + candidate under new seed.
      runBaselineAndCandidate();
      return;
    }
    if (name === 'reset') {
      ui.draft = { ...ui.baseline, seed: ui.draft.seed };
      ui.saveMessage = null;
      ui.saveError = null;
      renderRail(true);
      scheduleRun();
      return;
    }
    if (name === 'save') {
      saveExperiment();
    }
  });

  document.addEventListener('toggle', event => {
    const el = event.target;
    if (!(el instanceof HTMLDetailsElement)) return;
    if (el.classList.contains('studio-advanced')) {
      ui.showAdvanced = el.open;
    }
    const key = el.getAttribute('data-studio-depth');
    if (key && key in ui.depthOpen) ui.depthOpen[key] = el.open;
  }, true);
}

async function saveExperiment() {
  if (!ui.context.planId || !ui.result || ui.saveBusy) return;
  ui.saveBusy = true;
  ui.saveError = null;
  ui.saveMessage = null;
  renderRail(true);
  try {
    const changes = changedLevers(ui.draft, ui.baseline);
    const changeText = changes.length
      ? changes.map(c => `${c.label} ${c.from}→${c.to}`).join(', ')
      : ui.draft.simulation_mode === 'historical'
        ? `historical from ${ui.draft.simulation_historical_start_year}`
        : 'baseline refresh';
    const mc = ui.result?.monte_carlo || {};
    const title = `Studio · ${strengthHeadline(mc.plan_strength_label)} · ${new Date().toLocaleDateString('en-US')}`;
    const summary = [
      mc.plan_strength_summary || strengthExplain(mc.plan_strength_label),
      changeText !== 'baseline refresh' ? `Changed: ${changeText}.` : '',
      Number.isFinite(Number(mc.funded_trial_rate_pct))
        ? `${formatPct(mc.funded_trial_rate_pct)} of market histories lasted.`
        : '',
    ].filter(Boolean).join(' ');

    await api.savePlanSimulation(ui.context.planId, {
      title,
      source: 'simulation',
      summary,
      notes: 'Saved from Studio',
      input_payload: requestBody(ui.draft),
      result_payload: ui.result,
    });
    ui.saveMessage = 'Saved. Open Plan → Simulations to review it anytime.';
  } catch (err) {
    ui.saveError = err?.message || 'Could not save this experiment.';
  }
  ui.saveBusy = false;
  renderRail(true);
}
