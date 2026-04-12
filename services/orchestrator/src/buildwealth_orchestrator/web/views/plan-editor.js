import { fetchJson } from '../lib/api.js';
import { state, PLAN_SETTING_FIELDS, DIFF_SETTING_FIELDS } from '../lib/state.js';
import { byId, fmtCurrency, fmtDate, writeLog } from '../lib/utils.js';
import { collectSettingsPayload, setSettingsInputs } from '../lib/components.js';

const PROJECTION_SOURCE_OPTIONS = [
  { value: 'diff_base', label: 'Scenario Diff - Base' },
  { value: 'diff_candidate', label: 'Scenario Diff - Candidate' },
  { value: 'branch_base', label: 'Scenario Branch - Base' },
  { value: 'branch_branch', label: 'Scenario Branch - Branch' },
];

const ACCOUNT_TYPE_COLORS = {
  brokerage: '#2f6e47',
  cash: '#486f8f',
  checking: '#3a6f88',
  hsa: '#886a2d',
  '403b': '#9a4f39',
  '401k': '#6d5f8f',
  '457b': '#6e4f8f',
  ira: '#5a7d3a',
  roth_ira: '#4b7f64',
  roth_401k: '#4f6f90',
  traditional_ira: '#8b6c37',
  traditional_401k: '#7e4d4d',
  taxable: '#32608e',
  tax_free: '#4f8a66',
  tax_deferred: '#8a6b31',
};

const FALLBACK_ACCOUNT_TYPE_COLORS = ['#2f6e47', '#3e6f96', '#8a6018', '#7d4a4a', '#5f6f39', '#6d5f8f', '#4f7f7a', '#8a4f6a'];

const projectionState = {
  diffResult: null,
  branchResult: null,
  profilePayload: null,
  profileLoading: false,
};

function setControlsEnabled(enabled) {
  ['activate-plan', 'refresh-plan-context', 'save-plan', 'save-plan-timeline', 'save-plan-assumption-sets', 'save-plan-settings', 'run-scenario-diff', 'apply-scenario-overrides', 'run-scenario-branch', 'refresh-projection-profile', 'projection-source', 'projection-scenario-label', 'projection-account-metric', 'add-decision', 'plan-markdown', 'plan-tasks', 'plan-timeline', 'plan-assumption-sets', 'diff-assumption-set-id', 'diff-candidate-assumption-set-id', 'scenario-branch-name', 'branch-assumption-set-id', 'scenario-branch-events', 'decision-summary', 'decision-rationale', 'decision-status'].forEach(id => { const el = byId(id); if (el) el.disabled = !enabled; });
  for (const f of [...PLAN_SETTING_FIELDS, ...DIFF_SETTING_FIELDS]) { const el = byId(f.inputId); if (el) el.disabled = !enabled; }
}

function parseAssumptionSets(rawPayload) {
  let payload = {};
  if (typeof rawPayload === 'string') {
    const text = rawPayload.trim();
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = {};
      }
    }
  } else if (rawPayload && typeof rawPayload === 'object') {
    payload = rawPayload;
  }

  const rawSets = Array.isArray(payload.sets) ? payload.sets : [];
  const sets = [];
  const seen = new Set();
  for (const item of rawSets) {
    if (!item || typeof item !== 'object') continue;
    const id = String(item.id || '').trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    sets.push({ id, name: String(item.name || id).trim() || id });
  }

  return {
    activeId: String(payload.active_assumption_set_id || '').trim(),
    sets,
  };
}

function setAssumptionSetOptions(rawPayload) {
  const baseSelect = byId('diff-assumption-set-id');
  const candidateSelect = byId('diff-candidate-assumption-set-id');
  const branchSelect = byId('branch-assumption-set-id');
  if (!baseSelect || !candidateSelect || !branchSelect) return;

  const prevBase = String(baseSelect.value || '').trim();
  const prevCandidate = String(candidateSelect.value || '').trim();
  const prevBranch = String(branchSelect.value || '').trim();
  const parsed = parseAssumptionSets(rawPayload);

  baseSelect.innerHTML = '<option value="">Active plan set (default)</option>';
  candidateSelect.innerHTML = '<option value="">Same as base</option>';
  branchSelect.innerHTML = '<option value="">Active plan set (default)</option>';
  for (const set of parsed.sets) {
    const baseOption = document.createElement('option');
    baseOption.value = set.id;
    baseOption.textContent = `${set.name} (${set.id})`;
    baseSelect.appendChild(baseOption);

    const candidateOption = document.createElement('option');
    candidateOption.value = set.id;
    candidateOption.textContent = `${set.name} (${set.id})`;
    candidateSelect.appendChild(candidateOption);

    const branchOption = document.createElement('option');
    branchOption.value = set.id;
    branchOption.textContent = `${set.name} (${set.id})`;
    branchSelect.appendChild(branchOption);
  }

  const validIds = new Set(parsed.sets.map(s => s.id));
  const baseValue = validIds.has(prevBase) ? prevBase : (validIds.has(parsed.activeId) ? parsed.activeId : '');
  const candidateValue = validIds.has(prevCandidate) ? prevCandidate : '';
  const branchValue = validIds.has(prevBranch) ? prevBranch : '';
  baseSelect.value = baseValue;
  candidateSelect.value = candidateValue;
  branchSelect.value = branchValue;
}

function extractAssumptionSetSummary(resultPayload) {
  if (!resultPayload || typeof resultPayload !== 'object') return null;
  const scenarios = Array.isArray(resultPayload.scenarios) ? resultPayload.scenarios : [];
  const baseline = scenarios.find(item => item && item.label === 'baseline') || scenarios[0];
  const assumptions = baseline && typeof baseline === 'object' ? baseline.assumptions : null;
  if (!assumptions || typeof assumptions !== 'object') return null;
  const id = String(assumptions.assumption_set_id || '').trim() || null;
  const name = String(assumptions.assumption_set_name || '').trim() || null;
  if (!id && !name) return null;
  return { id, name };
}

function describeAssumptionSetSummary(summary) {
  if (!summary || typeof summary !== 'object') return 'Not available';
  const id = String(summary.id || '').trim();
  const name = String(summary.name || '').trim();
  if (id && name) return `${name} (${id})`;
  if (name) return name;
  if (id) return id;
  return 'Not available';
}

function resetProjectionState() {
  projectionState.diffResult = null;
  projectionState.branchResult = null;
  projectionState.profilePayload = null;
  projectionState.profileLoading = false;
}

function projectionSourceAvailable(optionValue) {
  if (optionValue === 'diff_base' || optionValue === 'diff_candidate') return !!projectionState.diffResult;
  if (optionValue === 'branch_base' || optionValue === 'branch_branch') return !!projectionState.branchResult;
  return false;
}

function setProjectionSourceOptions(preferredValue = '') {
  const select = byId('projection-source');
  if (!select) return '';

  const available = PROJECTION_SOURCE_OPTIONS.filter(item => projectionSourceAvailable(item.value));
  const current = String(select.value || '').trim();
  if (!available.length) {
    select.innerHTML = '<option value="">No scenario data yet</option>';
    select.value = '';
    return '';
  }

  select.innerHTML = '';
  for (const item of available) {
    const option = document.createElement('option');
    option.value = item.value;
    option.textContent = item.label;
    select.appendChild(option);
  }

  const next = available.some(item => item.value === preferredValue)
    ? preferredValue
    : available.some(item => item.value === current)
      ? current
      : available[0].value;
  select.value = next;
  return next;
}

function maybeLoadProjectionProfile(force = false) {
  if (force) {
    projectionState.profilePayload = null;
    projectionState.profileLoading = false;
  }
  if (projectionState.profilePayload || projectionState.profileLoading) return;
  if (!projectionState.diffResult && !projectionState.branchResult) return;

  projectionState.profileLoading = true;
  fetchJson('/api/financial-profile')
    .then((payload) => {
      projectionState.profilePayload = payload && typeof payload === 'object' ? payload : { physical_assets: [] };
    })
    .catch((error) => {
      projectionState.profilePayload = { physical_assets: [] };
      writeLog(`Projection profile load failed: ${error.message}`, null, true);
    })
    .finally(() => {
      projectionState.profileLoading = false;
      renderProjectionVisuals();
    });
}

function normalizeYear(raw) {
  const value = Number(raw);
  if (!Number.isFinite(value)) return null;
  return Math.trunc(value);
}

function yearFromIso(rawDate) {
  const text = String(rawDate || '').slice(0, 4);
  const value = Number(text);
  if (!Number.isFinite(value)) return null;
  return Math.trunc(value);
}

function projectionPlanningResultForSource(source) {
  if (source === 'diff_base') return projectionState.diffResult?.base_result || null;
  if (source === 'diff_candidate') return projectionState.diffResult?.candidate_result || null;
  if (source === 'branch_base') return projectionState.branchResult?.base_result || null;
  if (source === 'branch_branch') return projectionState.branchResult?.branch_result || null;
  return null;
}

function resolveScenarioFromPlanningResult(planningResult, preferredLabel) {
  const scenarios = Array.isArray(planningResult?.scenarios) ? planningResult.scenarios : [];
  if (!scenarios.length) return null;
  const resolved = scenarios.find(item => item && item.label === preferredLabel) || scenarios[0];
  if (!resolved || typeof resolved !== 'object') return null;
  return resolved;
}

function buildDebtBalanceSeries(years, debtProjection) {
  const series = new Map();
  const selected = debtProjection && typeof debtProjection === 'object' ? debtProjection.selected_scenario : null;
  const monthPoints = Array.isArray(selected?.month_points) ? selected.month_points : [];
  const byYear = new Map();
  for (const point of monthPoints) {
    const year = yearFromIso(point?.as_of);
    if (year === null) continue;
    const balance = Number(point?.total_balance_usd);
    if (!Number.isFinite(balance)) continue;
    byYear.set(year, Math.max(0, balance));
  }

  let lastValue = 0;
  for (const year of years) {
    if (byYear.has(year)) lastValue = Number(byYear.get(year));
    series.set(year, Math.max(0, lastValue));
  }
  return series;
}

function buildPhysicalAssetsSeries(years) {
  const series = new Map();
  if (!years.length) return series;

  const assets = Array.isArray(projectionState.profilePayload?.physical_assets)
    ? projectionState.profilePayload.physical_assets
    : [];
  if (!assets.length) {
    for (const year of years) series.set(year, 0);
    return series;
  }

  const startYear = years[0];
  for (const year of years) {
    const offset = Math.max(0, year - startYear);
    let total = 0;
    for (const asset of assets) {
      const currentValue = Number(asset?.current_value_usd);
      if (!Number.isFinite(currentValue) || currentValue <= 0) continue;
      const growthRateRaw = Number(asset?.annual_growth_rate);
      const growthRate = Number.isFinite(growthRateRaw) ? Math.max(-0.95, Math.min(1.0, growthRateRaw)) : 0;
      total += currentValue * ((1 + growthRate) ** offset);
    }
    series.set(year, total);
  }

  return series;
}

function buildNetWorthSeries(timelinePoints, debtProjection) {
  const years = [];
  for (const point of timelinePoints) {
    const year = normalizeYear(point?.year);
    if (year === null) continue;
    years.push(year);
  }

  years.sort((a, b) => a - b);
  const uniqueYears = years.filter((value, index) => index === 0 || value !== years[index - 1]);
  if (!uniqueYears.length) return [];

  const debtByYear = buildDebtBalanceSeries(uniqueYears, debtProjection);
  const physicalAssetsByYear = buildPhysicalAssetsSeries(uniqueYears);
  const timelineByYear = new Map();
  for (const point of timelinePoints) {
    const year = normalizeYear(point?.year);
    if (year === null) continue;
    timelineByYear.set(year, point);
  }

  return uniqueYears.map((year) => {
    const point = timelineByYear.get(year) || {};
    const portfolio = Number(point?.ending_balance_usd);
    const portfolioReal = Number(point?.ending_balance_real_usd);
    const debtBalance = Number(debtByYear.get(year) || 0);
    const physicalAssets = Number(physicalAssetsByYear.get(year) || 0);
    const resolvedPortfolio = Number.isFinite(portfolio) ? portfolio : 0;
    const resolvedReal = Number.isFinite(portfolioReal) ? portfolioReal : resolvedPortfolio;
    return {
      year,
      portfolio: resolvedPortfolio,
      portfolio_real: resolvedReal,
      debt_balance: debtBalance,
      physical_assets: physicalAssets,
      net_worth: resolvedPortfolio + physicalAssets - debtBalance,
    };
  });
}

function buildLinePath(points, valueKey, toY) {
  return points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${toY(Number(point[valueKey] || 0)).toFixed(2)}`).join(' ');
}

function renderNetWorthChart(series) {
  const chart = byId('plan-net-worth-chart');
  if (!chart) return;
  if (!Array.isArray(series) || !series.length) {
    chart.innerHTML = '';
    return;
  }

  const width = 760;
  const height = 220;
  const left = 44;
  const right = 18;
  const top = 14;
  const bottom = 30;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;

  let minValue = Number.POSITIVE_INFINITY;
  let maxValue = Number.NEGATIVE_INFINITY;
  for (const row of series) {
    for (const key of ['net_worth', 'portfolio', 'physical_assets', 'debt_balance']) {
      const value = Number(row[key]);
      if (!Number.isFinite(value)) continue;
      minValue = Math.min(minValue, value);
      maxValue = Math.max(maxValue, value);
    }
  }
  if (!Number.isFinite(minValue) || !Number.isFinite(maxValue)) {
    chart.innerHTML = '';
    return;
  }
  if (minValue === maxValue) {
    const pad = Math.max(1, Math.abs(minValue) * 0.1);
    minValue -= pad;
    maxValue += pad;
  }
  const valueRange = maxValue - minValue;

  const toY = value => top + ((maxValue - value) / valueRange) * plotHeight;
  const points = series.map((row, index) => ({
    ...row,
    x: left + (series.length === 1 ? 0 : (index / (series.length - 1)) * plotWidth),
  }));

  const netWorthPath = buildLinePath(points, 'net_worth', toY);
  const portfolioPath = buildLinePath(points, 'portfolio', toY);
  const physicalPath = buildLinePath(points, 'physical_assets', toY);
  const debtPath = buildLinePath(points, 'debt_balance', toY);

  const grid = [];
  const ticks = 4;
  for (let i = 0; i <= ticks; i += 1) {
    const ratio = i / ticks;
    const y = top + ratio * plotHeight;
    const tickValue = maxValue - ratio * valueRange;
    grid.push(`<line x1="${left}" y1="${y.toFixed(2)}" x2="${(left + plotWidth).toFixed(2)}" y2="${y.toFixed(2)}" class="projection-grid-line"></line>`);
    grid.push(`<text x="4" y="${(y + 4).toFixed(2)}" class="projection-axis-label">${fmtCurrency(tickValue)}</text>`);
  }

  if (minValue < 0 && maxValue > 0) {
    const zeroY = toY(0);
    grid.push(`<line x1="${left}" y1="${zeroY.toFixed(2)}" x2="${(left + plotWidth).toFixed(2)}" y2="${zeroY.toFixed(2)}" class="projection-zero-line"></line>`);
  }

  const firstYear = series[0]?.year || '-';
  const lastYear = series[series.length - 1]?.year || '-';
  chart.innerHTML = `
    ${grid.join('')}
    <path d="${netWorthPath}" class="projection-line projection-line-net-worth"></path>
    <path d="${portfolioPath}" class="projection-line projection-line-portfolio"></path>
    <path d="${physicalPath}" class="projection-line projection-line-physical"></path>
    <path d="${debtPath}" class="projection-line projection-line-debt"></path>
    <text x="${left}" y="${height - 8}" class="projection-axis-label">${firstYear}</text>
    <text x="${(left + plotWidth - 40).toFixed(2)}" y="${height - 8}" class="projection-axis-label">${lastYear}</text>
  `;
}

function accountTypeColor(accountType, index) {
  const key = String(accountType || '').trim().toLowerCase();
  if (Object.prototype.hasOwnProperty.call(ACCOUNT_TYPE_COLORS, key)) return ACCOUNT_TYPE_COLORS[key];
  return FALLBACK_ACCOUNT_TYPE_COLORS[index % FALLBACK_ACCOUNT_TYPE_COLORS.length];
}

function buildAccountMetricSeries(accountPoints, metricKey) {
  const byYear = new Map();
  const accountTypes = new Set();
  for (const point of accountPoints) {
    const year = normalizeYear(point?.year);
    if (year === null) continue;
    const accountType = String(point?.account_type || 'unknown').trim() || 'unknown';
    const rawValue = Number(point?.[metricKey]);
    const value = Number.isFinite(rawValue) ? rawValue : 0;
    if (!byYear.has(year)) byYear.set(year, {});
    const bucket = byYear.get(year);
    bucket[accountType] = Number(bucket[accountType] || 0) + value;
    accountTypes.add(accountType);
  }

  const years = [...byYear.keys()].sort((a, b) => a - b);
  const types = [...accountTypes].sort((a, b) => a.localeCompare(b));
  const rows = years.map((year) => {
    const values = byYear.get(year) || {};
    let positiveTotal = 0;
    let negativeTotal = 0;
    for (const type of types) {
      const value = Number(values[type] || 0);
      if (value >= 0) positiveTotal += value;
      else negativeTotal += value;
    }
    return {
      year,
      values,
      positive_total: positiveTotal,
      negative_total: negativeTotal,
    };
  });

  return { rows, types };
}

function renderAccountTypeChart(accountPoints, metricKey) {
  const chart = byId('plan-account-type-chart');
  const legend = byId('plan-account-type-legend');
  if (!chart || !legend) return;

  const series = buildAccountMetricSeries(accountPoints, metricKey);
  if (!series.rows.length || !series.types.length) {
    chart.innerHTML = '';
    legend.innerHTML = '';
    return;
  }

  const width = 760;
  const height = 220;
  const left = 44;
  const right = 18;
  const top = 14;
  const bottom = 30;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;

  const maxValue = Math.max(0, ...series.rows.map(item => item.positive_total));
  const minValue = Math.min(0, ...series.rows.map(item => item.negative_total));
  const range = Math.max(1, maxValue - minValue);
  const toY = value => top + ((maxValue - value) / range) * plotHeight;

  const bars = [];
  const yearSpan = plotWidth / Math.max(1, series.rows.length);
  const barWidth = Math.max(6, yearSpan * 0.66);

  for (let rowIndex = 0; rowIndex < series.rows.length; rowIndex += 1) {
    const row = series.rows[rowIndex];
    const x = left + rowIndex * yearSpan + ((yearSpan - barWidth) / 2);
    let positiveCursor = 0;
    let negativeCursor = 0;

    for (let typeIndex = 0; typeIndex < series.types.length; typeIndex += 1) {
      const type = series.types[typeIndex];
      const value = Number(row.values[type] || 0);
      if (!value) continue;

      let start = 0;
      let end = 0;
      if (value > 0) {
        start = positiveCursor;
        positiveCursor += value;
        end = positiveCursor;
      } else {
        start = negativeCursor;
        negativeCursor += value;
        end = negativeCursor;
      }

      const y1 = toY(start);
      const y2 = toY(end);
      const y = Math.min(y1, y2);
      const h = Math.max(1, Math.abs(y1 - y2));
      bars.push(`<rect x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${barWidth.toFixed(2)}" height="${h.toFixed(2)}" fill="${accountTypeColor(type, typeIndex)}" opacity="0.86"></rect>`);
    }
  }

  const grid = [];
  const ticks = 4;
  for (let i = 0; i <= ticks; i += 1) {
    const ratio = i / ticks;
    const y = top + ratio * plotHeight;
    const tickValue = maxValue - ratio * range;
    grid.push(`<line x1="${left}" y1="${y.toFixed(2)}" x2="${(left + plotWidth).toFixed(2)}" y2="${y.toFixed(2)}" class="projection-grid-line"></line>`);
    grid.push(`<text x="4" y="${(y + 4).toFixed(2)}" class="projection-axis-label">${fmtCurrency(tickValue)}</text>`);
  }

  if (minValue < 0 && maxValue > 0) {
    const zeroY = toY(0);
    grid.push(`<line x1="${left}" y1="${zeroY.toFixed(2)}" x2="${(left + plotWidth).toFixed(2)}" y2="${zeroY.toFixed(2)}" class="projection-zero-line"></line>`);
  }

  const firstYear = series.rows[0]?.year || '-';
  const lastYear = series.rows[series.rows.length - 1]?.year || '-';
  chart.innerHTML = `
    ${grid.join('')}
    ${bars.join('')}
    <text x="${left}" y="${height - 8}" class="projection-axis-label">${firstYear}</text>
    <text x="${(left + plotWidth - 40).toFixed(2)}" y="${height - 8}" class="projection-axis-label">${lastYear}</text>
  `;

  legend.innerHTML = series.types.map((type, index) => (
    `<span class="projection-legend-item"><span class="projection-legend-swatch" style="background:${accountTypeColor(type, index)}"></span>${type}</span>`
  )).join('');
}

function renderProjectionAccountTable(accountPoints) {
  const tbody = byId('projection-account-body');
  if (!tbody) return;

  const byAccount = new Map();
  for (const point of accountPoints) {
    const accountId = String(point?.account_id || '').trim();
    if (!accountId) continue;
    const year = normalizeYear(point?.year);
    const ending = Number(point?.ending_balance_usd);
    const contribution = Number(point?.contribution_usd);
    const growth = Number(point?.growth_usd);
    const withdrawal = Number(point?.withdrawal_usd);

    if (!byAccount.has(accountId)) {
      byAccount.set(accountId, {
        account_id: accountId,
        account_type: String(point?.account_type || 'unknown'),
        latest_year: year === null ? -1 : year,
        final_balance: Number.isFinite(ending) ? ending : 0,
        contributions: 0,
        growth: 0,
        withdrawals: 0,
      });
    }

    const row = byAccount.get(accountId);
    if (year !== null && year >= row.latest_year && Number.isFinite(ending)) {
      row.latest_year = year;
      row.final_balance = ending;
    }
    if (Number.isFinite(contribution)) row.contributions += contribution;
    if (Number.isFinite(growth)) row.growth += growth;
    if (Number.isFinite(withdrawal)) row.withdrawals += withdrawal;
  }

  const rows = [...byAccount.values()].sort((a, b) => b.final_balance - a.final_balance);
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="6">No projection data yet.</td></tr>';
    return;
  }

  tbody.innerHTML = '';
  for (const row of rows) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><code>${row.account_id}</code></td>
      <td>${row.account_type || 'unknown'}</td>
      <td>${fmtCurrency(row.final_balance || 0)}</td>
      <td>${fmtCurrency(row.contributions || 0)}</td>
      <td>${fmtCurrency(row.growth || 0)}</td>
      <td>${fmtCurrency(row.withdrawals || 0)}</td>`;
    tbody.appendChild(tr);
  }
}

function renderProjectionVisuals() {
  const summary = byId('projection-summary');
  if (!summary) return;

  const selectedSource = setProjectionSourceOptions();
  if (!selectedSource) {
    summary.textContent = 'Run a scenario diff or branch to populate projection visuals.';
    renderNetWorthChart([]);
    renderAccountTypeChart([], 'ending_balance_usd');
    renderProjectionAccountTable([]);
    return;
  }

  maybeLoadProjectionProfile();

  const scenarioLabel = String(byId('projection-scenario-label')?.value || 'baseline').trim() || 'baseline';
  const metricKey = String(byId('projection-account-metric')?.value || 'ending_balance_usd').trim() || 'ending_balance_usd';
  const planningResult = projectionPlanningResultForSource(selectedSource);
  const scenario = resolveScenarioFromPlanningResult(planningResult, scenarioLabel);
  if (!planningResult || !scenario) {
    summary.textContent = 'Selected projection source does not include scenario data.';
    renderNetWorthChart([]);
    renderAccountTypeChart([], metricKey);
    renderProjectionAccountTable([]);
    return;
  }

  const timelinePoints = Array.isArray(scenario.timeline_points) ? scenario.timeline_points : [];
  const accountPoints = Array.isArray(scenario.account_balance_points) ? scenario.account_balance_points : [];
  if (!timelinePoints.length) {
    summary.textContent = 'No timeline points available for this scenario.';
    renderNetWorthChart([]);
    renderAccountTypeChart([], metricKey);
    renderProjectionAccountTable([]);
    return;
  }

  const netWorthSeries = buildNetWorthSeries(timelinePoints, planningResult?.debt_projection);
  renderNetWorthChart(netWorthSeries);
  renderAccountTypeChart(accountPoints, metricKey);
  renderProjectionAccountTable(accountPoints);

  const sourceLabel = PROJECTION_SOURCE_OPTIONS.find(item => item.value === selectedSource)?.label || selectedSource;
  const finalPoint = netWorthSeries[netWorthSeries.length - 1] || {};
  const firstYear = netWorthSeries[0]?.year;
  const lastYear = finalPoint?.year;
  const metricLabel = metricKey === 'contribution_usd'
    ? 'Contributions'
    : metricKey === 'growth_usd'
      ? 'Growth'
      : 'Ending Balance';
  summary.textContent = `${sourceLabel} • ${String(scenario.label || scenarioLabel)} • ${firstYear || '-'} to ${lastYear || '-'} • Final net worth ${fmtCurrency(finalPoint.net_worth || 0)} • Account metric: ${metricLabel}`;
}

export function clearDetail() {
  state.currentPlanDetail = null;
  byId('plan-meta').textContent = 'Select a plan to view details.';
  byId('plan-settings-meta').textContent = 'Blank values use global defaults from planner configuration.';
  ['plan-markdown', 'plan-tasks', 'plan-timeline', 'plan-assumption-sets', 'plan-context', 'scenario-diff-output', 'scenario-branch-name', 'scenario-branch-events', 'scenario-branch-output', 'artifact-content'].forEach(id => { const el = byId(id); if (el) el.value = ''; });
  byId('scenario-diff-summary').textContent = 'No scenario diff run yet.';
  byId('scenario-branch-summary').textContent = 'No scenario branch run yet.';
  byId('projection-summary').textContent = 'Run a scenario diff or branch to populate projection visuals.';
  byId('plan-decisions-body').innerHTML = '<tr><td colspan="4">No decisions yet.</td></tr>';
  byId('plan-artifacts-body').innerHTML = '<tr><td colspan="4">No artifacts yet.</td></tr>';
  byId('projection-account-body').innerHTML = '<tr><td colspan="6">No projection data yet.</td></tr>';
  setSettingsInputs(PLAN_SETTING_FIELDS, {});
  setSettingsInputs(DIFF_SETTING_FIELDS, {});
  const scenarioLabelSelect = byId('projection-scenario-label');
  if (scenarioLabelSelect) scenarioLabelSelect.value = 'baseline';
  const metricSelect = byId('projection-account-metric');
  if (metricSelect) metricSelect.value = 'ending_balance_usd';
  resetProjectionState();
  setAssumptionSetOptions({});
  setProjectionSourceOptions();
  renderNetWorthChart([]);
  renderAccountTypeChart([], 'ending_balance_usd');
  setControlsEnabled(false);
}

export function renderDetail() {
  const d = state.currentPlanDetail;
  if (!d) { clearDetail(); return; }
  resetProjectionState();
  byId('plan-meta').textContent = `${d.title || 'Untitled'} \u2022 ${d.is_active ? 'Active Plan' : 'Inactive'} \u2022 Updated ${fmtDate(d.updated_at)}`;
  byId('plan-markdown').value = d.files?.plan_markdown || '';
  byId('plan-tasks').value = d.files?.tasks_markdown || '';
  byId('plan-timeline').value = d.files?.timeline_json || '';
  byId('plan-assumption-sets').value = d.files?.assumption_sets_json || '';
  setAssumptionSetOptions(d.files?.assumption_sets_json || '');
  byId('plan-context').value = d.files?.context_markdown || '';
  byId('scenario-diff-summary').textContent = 'No scenario diff run yet.';
  byId('scenario-diff-output').value = '';
  byId('scenario-branch-summary').textContent = 'No scenario branch run yet.';
  byId('scenario-branch-output').value = '';
  byId('scenario-branch-name').value = '';
  byId('scenario-branch-events').value = '';
  byId('projection-summary').textContent = 'Run a scenario diff or branch to populate projection visuals.';
  byId('projection-account-body').innerHTML = '<tr><td colspan="6">No projection data yet.</td></tr>';
  const scenarioLabelSelect = byId('projection-scenario-label');
  if (scenarioLabelSelect) scenarioLabelSelect.value = 'baseline';
  const metricSelect = byId('projection-account-metric');
  if (metricSelect) metricSelect.value = 'ending_balance_usd';
  setProjectionSourceOptions();
  renderNetWorthChart([]);
  renderAccountTypeChart([], 'ending_balance_usd');
  setSettingsInputs(PLAN_SETTING_FIELDS, d.settings || {});
  const su = d.settings?.updated_at ? fmtDate(d.settings.updated_at) : null;
  byId('plan-settings-meta').textContent = su ? `Settings updated ${su}` : 'Blank values use global defaults from planner configuration.';
  renderDecisions(Array.isArray(d.decisions) ? d.decisions : []);
  renderArtifacts(Array.isArray(d.artifacts) ? d.artifacts : []);
  byId('artifact-content').value = '';
  setControlsEnabled(true);
}

function renderDecisions(decisions) {
  const tbody = byId('plan-decisions-body');
  tbody.innerHTML = '';
  if (!decisions.length) { tbody.innerHTML = '<tr><td colspan="4">No decisions yet.</td></tr>'; return; }
  for (const d of decisions) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${fmtDate(d.created_at)}</td><td>${d.status || 'proposed'}</td><td>${d.summary || '-'}</td><td>${d.rationale || '-'}</td>`;
    tbody.appendChild(tr);
  }
}

function renderArtifacts(artifacts) {
  const tbody = byId('plan-artifacts-body');
  tbody.innerHTML = '';
  if (!artifacts.length) { tbody.innerHTML = '<tr><td colspan="4">No artifacts yet.</td></tr>'; return; }
  for (const a of artifacts) {
    const tr = document.createElement('tr');
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'ghost small'; btn.textContent = 'Open';
    btn.addEventListener('click', () => loadArtifact(a.id).catch(e => writeLog(`Artifact load failed: ${e.message}`, null, true)));
    tr.innerHTML = `<td>${fmtDate(a.created_at)}</td><td>${a.title || '-'}</td><td>${a.file_name || '-'}</td><td></td>`;
    tr.lastElementChild.appendChild(btn);
    tbody.appendChild(tr);
  }
}

async function loadArtifact(artifactId) {
  if (!state.currentPlanId || !artifactId) return;
  const a = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/artifacts/${encodeURIComponent(artifactId)}`);
  byId('artifact-content').value = a.content || '';
}

function formatDiffOutput(diff) {
  const rows = Array.isArray(diff?.scenario_deltas) ? diff.scenario_deltas : [];
  const lines = [`Plan: ${diff?.plan_id || '-'}`, `Current Portfolio: ${fmtCurrency(diff?.current_portfolio_value_usd)}`, '', 'Scenario Delta (Candidate - Base):'];
  if (!rows.length) lines.push('- No deltas.');
  else for (const r of rows) lines.push(`- ${r.label}: Future ${fmtCurrency(r.delta_future_value_usd)}, Real ${fmtCurrency(r.delta_real_value_usd)}`);

  const baseAssumptionSet = diff?.base_assumption_set || extractAssumptionSetSummary(diff?.base_result);
  const candidateAssumptionSet = diff?.candidate_assumption_set || extractAssumptionSetSummary(diff?.candidate_result);
  lines.push('', 'Assumption Set Context:');
  if (!baseAssumptionSet && !candidateAssumptionSet) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeAssumptionSetSummary(baseAssumptionSet)}`);
    lines.push(`- Candidate: ${describeAssumptionSetSummary(candidateAssumptionSet)}`);
  }

  const baseIncome = diff?.base_result?.income_projection;
  const candidateIncome = diff?.candidate_result?.income_projection;
  lines.push('', 'Income Projection Context:');
  if (!baseIncome && !candidateIncome) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeIncomeProjection(baseIncome)}`);
    lines.push(`- Candidate: ${describeIncomeProjection(candidateIncome)}`);
  }

  const baseExpenses = diff?.base_result?.expense_projection;
  const candidateExpenses = diff?.candidate_result?.expense_projection;
  lines.push('', 'Expense Projection Context:');
  if (!baseExpenses && !candidateExpenses) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeExpenseProjection(baseExpenses)}`);
    lines.push(`- Candidate: ${describeExpenseProjection(candidateExpenses)}`);
  }

  const baseDebt = diff?.base_result?.debt_projection;
  const candidateDebt = diff?.candidate_result?.debt_projection;
  lines.push('', 'Debt Projection Context:');
  if (!baseDebt && !candidateDebt) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeDebtProjection(baseDebt)}`);
    lines.push(`- Candidate: ${describeDebtProjection(candidateDebt)}`);
  }

  const baseTimeline = diff?.base_result?.timeline_projection;
  const candidateTimeline = diff?.candidate_result?.timeline_projection;
  lines.push('', 'Timeline Impact Context:');
  if (!baseTimeline && !candidateTimeline) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeTimelineProjection(baseTimeline)}`);
    lines.push(`- Candidate: ${describeTimelineProjection(candidateTimeline)}`);
  }

  const baseSocialSecurity = diff?.base_result?.social_security_projection;
  const candidateSocialSecurity = diff?.candidate_result?.social_security_projection;
  lines.push('', 'Social Security Context:');
  if (!baseSocialSecurity && !candidateSocialSecurity) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeSocialSecurityProjection(baseSocialSecurity)}`);
    lines.push(`- Candidate: ${describeSocialSecurityProjection(candidateSocialSecurity)}`);
  }

  const baseRmd = diff?.base_result?.rmd_projection;
  const candidateRmd = diff?.candidate_result?.rmd_projection;
  lines.push('', 'RMD Context:');
  if (!baseRmd && !candidateRmd) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeRmdProjection(baseRmd)}`);
    lines.push(`- Candidate: ${describeRmdProjection(candidateRmd)}`);
  }

  const mc = diff?.monte_carlo_delta || {};
  lines.push('', 'Monte Carlo Delta:', `- P10: ${fmtCurrency(mc.delta_p10_future_value_usd)}`, `- P50: ${fmtCurrency(mc.delta_p50_future_value_usd)}`, `- P90: ${fmtCurrency(mc.delta_p90_future_value_usd)}`);
  lines.push('', 'Raw Payload:', JSON.stringify(diff, null, 2));
  return lines.join('\n');
}

function formatBranchOutput(branch) {
  const rows = Array.isArray(branch?.scenario_deltas) ? branch.scenario_deltas : [];
  const lines = [
    `Plan: ${branch?.plan_id || '-'}`,
    `Branch: ${branch?.branch_name || '-'}`,
    `Current Portfolio: ${fmtCurrency(branch?.current_portfolio_value_usd)}`,
    '',
    'Scenario Delta (Branch - Base):',
  ];
  if (!rows.length) lines.push('- No deltas.');
  else for (const row of rows) lines.push(`- ${row.label}: Future ${fmtCurrency(row.delta_future_value_usd)}, Real ${fmtCurrency(row.delta_real_value_usd)}`);

  lines.push('', 'Assumption Set Context:', `- ${describeAssumptionSetSummary(branch?.assumption_set || extractAssumptionSetSummary(branch?.base_result))}`);

  const events = Array.isArray(branch?.branch_events) ? branch.branch_events : [];
  lines.push('', 'Branch Events:');
  if (!events.length) {
    lines.push('- None.');
  } else {
    for (const event of events) {
      const dateLabel = String(event?.date || '?');
      const label = String(event?.label || 'Branch Event');
      const eventType = String(event?.event_type || 'milestone');
      const impactType = String(event?.impact_type || 'expense');
      const recurrence = String(event?.recurring_frequency || 'one_time');
      const amount = fmtCurrency(event?.amount_usd);
      const endDate = String(event?.end_date || '').trim();
      const period = endDate ? `${dateLabel} -> ${endDate}` : dateLabel;
      lines.push(`- ${period}: ${label} (${eventType}, ${impactType}, ${recurrence}, ${amount})`);
    }
  }

  lines.push('', 'Timeline Impact Context:');
  lines.push(`- Base: ${describeTimelineProjection(branch?.base_result?.timeline_projection)}`);
  lines.push(`- Branch: ${describeTimelineProjection(branch?.branch_result?.timeline_projection)}`);

  const mc = branch?.monte_carlo_delta || {};
  lines.push('', 'Monte Carlo Delta:', `- P10: ${fmtCurrency(mc.delta_p10_future_value_usd)}`, `- P50: ${fmtCurrency(mc.delta_p50_future_value_usd)}`, `- P90: ${fmtCurrency(mc.delta_p90_future_value_usd)}`);
  lines.push('', 'Raw Payload:', JSON.stringify(branch, null, 2));
  return lines.join('\n');
}

function describeIncomeProjection(projection) {
  if (!projection || typeof projection !== 'object') return 'Not available';
  const firstYear = fmtCurrency(projection.first_year_gross_income_usd);
  const finalYear = fmtCurrency(projection.final_year_gross_income_usd);
  const years = Number(projection.years);
  const yearsLabel = Number.isFinite(years) && years > 0 ? `${Math.trunc(years)}y` : 'n/a';
  const growth = Number(projection.annualized_income_growth_rate);
  const growthLabel = Number.isFinite(growth) ? `${(growth * 100).toFixed(2)}%` : 'n/a';
  return `${firstYear} -> ${finalYear} (${yearsLabel}, annualized ${growthLabel})`;
}

function describeExpenseProjection(projection) {
  if (!projection || typeof projection !== 'object') return 'Not available';
  const firstYear = fmtCurrency(projection.first_year_expenses_usd);
  const finalYear = fmtCurrency(projection.final_year_expenses_usd);
  const years = Number(projection.years);
  const yearsLabel = Number.isFinite(years) && years > 0 ? `${Math.trunc(years)}y` : 'n/a';
  const growth = Number(projection.annualized_expense_growth_rate);
  const growthLabel = Number.isFinite(growth) ? `${(growth * 100).toFixed(2)}%` : 'n/a';
  return `${firstYear} -> ${finalYear} (${yearsLabel}, annualized ${growthLabel})`;
}

function describeDebtProjection(projection) {
  if (!projection || typeof projection !== 'object') return 'Not available';
  const selected = projection.selected_scenario || {};
  const strategy = String(projection.strategy || selected.strategy || 'minimum');
  const months = Number(selected.months_to_payoff);
  const remaining = fmtCurrency(selected.remaining_balance_usd);
  const interest = fmtCurrency(selected.total_interest_paid_usd);
  const paidOffLabel = selected.paid_off ? 'paid off' : `remaining ${remaining}`;
  const monthsLabel = Number.isFinite(months) && months > 0 ? `${Math.trunc(months)}m` : 'n/a';
  return `${strategy} (${monthsLabel}, ${paidOffLabel}, interest ${interest})`;
}

function describeTimelineProjection(projection) {
  if (!projection || typeof projection !== 'object') return 'Not available';
  const eventsCount = Number(projection.events_count);
  const years = Number(projection.years);
  const firstYearNet = fmtCurrency(projection.yearly_points?.[0]?.net_cashflow_impact_usd);
  const cumulative = fmtCurrency(projection.cumulative_net_cashflow_impact_usd);
  const eventsLabel = Number.isFinite(eventsCount) ? `${Math.trunc(eventsCount)} event(s)` : 'n/a events';
  const yearsLabel = Number.isFinite(years) ? `${Math.trunc(years)}y` : 'n/a';
  return `${eventsLabel}, first-year net ${firstYearNet}, cumulative net ${cumulative} (${yearsLabel})`;
}

function describeSocialSecurityProjection(projection) {
  if (!projection || typeof projection !== 'object') return 'Not available';
  const selectedAge = Number(projection.selected_claiming_age);
  const optimalAge = Number(projection.optimal_claiming_age);
  const annual = fmtCurrency(projection.selected_annual_benefit_usd);
  const fraMonthly = fmtCurrency(projection.fra_monthly_benefit_usd);
  const selectedAgeLabel = Number.isFinite(selectedAge) ? `age ${Math.trunc(selectedAge)}` : 'n/a';
  const optimalAgeLabel = Number.isFinite(optimalAge) ? `optimal ${Math.trunc(optimalAge)}` : 'optimal n/a';
  return `${selectedAgeLabel} (${optimalAgeLabel}), annual ${annual}, FRA monthly ${fraMonthly}`;
}

function describeRmdProjection(projection) {
  if (!projection || typeof projection !== 'object') return 'Not available';
  const startAge = Number(projection.rmd_start_age);
  const totalProjected = fmtCurrency(projection.total_projected_rmds_usd);
  const firstYear = fmtCurrency(projection.yearly_points?.[0]?.total_rmd_usd);
  const eligibleAccounts = Number(projection.eligible_account_count);
  const startAgeLabel = Number.isFinite(startAge) ? `start age ${Math.trunc(startAge)}` : 'start age n/a';
  const accountLabel = Number.isFinite(eligibleAccounts) ? `${Math.trunc(eligibleAccounts)} account(s)` : 'n/a account(s)';
  return `${startAgeLabel}, first-year ${firstYear}, projected total ${totalProjected}, ${accountLabel}`;
}

export function initEditor(refreshPlans) {
  byId('projection-source').addEventListener('change', () => renderProjectionVisuals());
  byId('projection-scenario-label').addEventListener('change', () => renderProjectionVisuals());
  byId('projection-account-metric').addEventListener('change', () => renderProjectionVisuals());
  byId('refresh-projection-profile').addEventListener('click', () => {
    maybeLoadProjectionProfile(true);
    renderProjectionVisuals();
  });

  byId('save-plan').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    writeLog(`Saving plan ${state.currentPlanId}...`);
    try {
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}`, { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ plan_markdown: byId('plan-markdown').value, tasks_markdown: byId('plan-tasks').value }) });
      await refreshPlans(); renderDetail(); writeLog('Plan saved.');
    } catch (e) { writeLog(`Save failed: ${e.message}`, null, true); }
  });

  byId('save-plan-timeline').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    const raw = byId('plan-timeline').value.trim();
    let payload;
    try {
      payload = raw ? JSON.parse(raw) : { events: [], retirement: {} };
    } catch (e) {
      writeLog(`Timeline JSON is invalid: ${e.message}`, null, true);
      return;
    }
    writeLog('Saving timeline...', payload);
    try {
      await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/timeline`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}`);
      renderDetail();
      await refreshPlans();
      writeLog('Timeline saved.');
    } catch (e) {
      writeLog(`Save timeline failed: ${e.message}`, null, true);
    }
  });

  byId('save-plan-assumption-sets').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    const raw = byId('plan-assumption-sets').value.trim();
    let payload;
    try {
      payload = raw ? JSON.parse(raw) : {};
    } catch (e) {
      writeLog(`Assumption sets JSON is invalid: ${e.message}`, null, true);
      return;
    }
    writeLog('Saving assumption sets...', payload);
    try {
      await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/assumption-sets`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}`);
      renderDetail();
      await refreshPlans();
      writeLog('Assumption sets saved.');
    } catch (e) {
      writeLog(`Save assumption sets failed: ${e.message}`, null, true);
    }
  });

  byId('save-plan-settings').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    let payload; try { payload = collectSettingsPayload(PLAN_SETTING_FIELDS, { includeNulls: true }); } catch (e) { writeLog(e.message, null, true); return; }
    writeLog(`Saving settings...`, payload);
    try {
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/settings`, { method: 'PATCH', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
      renderDetail(); await refreshPlans(); writeLog('Settings saved.');
    } catch (e) { writeLog(`Save settings failed: ${e.message}`, null, true); }
  });

  byId('run-scenario-diff').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    let compare; try { compare = collectSettingsPayload(DIFF_SETTING_FIELDS, { includeNulls: false }); } catch (e) { writeLog(e.message, null, true); return; }
    const assumptionSetId = String(byId('diff-assumption-set-id')?.value || '').trim();
    const candidateAssumptionSetId = String(byId('diff-candidate-assumption-set-id')?.value || '').trim();
    const payload = { compare_settings: compare };
    if (assumptionSetId) payload.assumption_set_id = assumptionSetId;
    if (candidateAssumptionSetId) payload.candidate_assumption_set_id = candidateAssumptionSetId;
    writeLog('Running scenario diff...', payload);
    try {
      const result = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/scenario-diff`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
      const bl = (result.scenario_deltas || []).find(r => r.label === 'baseline');
      byId('scenario-diff-summary').textContent = bl ? `Baseline delta: ${fmtCurrency(bl.delta_future_value_usd)} (real: ${fmtCurrency(bl.delta_real_value_usd)})` : 'Diff completed.';
      byId('scenario-diff-output').value = formatDiffOutput(result);
      projectionState.diffResult = result;
      setProjectionSourceOptions('diff_base');
      renderProjectionVisuals();
      writeLog('Scenario diff completed.');
    } catch (e) { writeLog(`Diff failed: ${e.message}`, null, true); byId('scenario-diff-summary').textContent = `Failed: ${e.message}`; }
  });

  byId('run-scenario-branch').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }

    const branchName = String(byId('scenario-branch-name')?.value || '').trim() || 'What-If Branch';
    const assumptionSetId = String(byId('branch-assumption-set-id')?.value || '').trim();
    const branchEventsRaw = String(byId('scenario-branch-events')?.value || '').trim();

    let branchEvents = [];
    if (branchEventsRaw) {
      try {
        branchEvents = JSON.parse(branchEventsRaw);
      } catch (e) {
        writeLog(`Branch events JSON is invalid: ${e.message}`, null, true);
        return;
      }
      if (!Array.isArray(branchEvents)) {
        writeLog('Branch events JSON must be an array.', null, true);
        return;
      }
    }

    let compareSettings = {};
    try {
      compareSettings = collectSettingsPayload(DIFF_SETTING_FIELDS, { includeNulls: false });
    } catch (e) {
      writeLog(e.message, null, true);
      return;
    }

    if (!branchEvents.length && !Object.keys(compareSettings).length) {
      writeLog('Provide at least one branch event or override field.', null, true);
      return;
    }

    const payload = {
      branch_name: branchName,
      branch_events: branchEvents,
    };
    if (assumptionSetId) payload.assumption_set_id = assumptionSetId;
    if (Object.keys(compareSettings).length) payload.compare_settings = compareSettings;

    writeLog('Running scenario branch...', payload);
    try {
      const result = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/scenario-branch`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
      const bl = (result.scenario_deltas || []).find(r => r.label === 'baseline');
      byId('scenario-branch-summary').textContent = bl ? `Baseline delta: ${fmtCurrency(bl.delta_future_value_usd)} (real: ${fmtCurrency(bl.delta_real_value_usd)})` : 'Branch completed.';
      byId('scenario-branch-output').value = formatBranchOutput(result);
      projectionState.branchResult = result;
      setProjectionSourceOptions('branch_branch');
      renderProjectionVisuals();
      writeLog('Scenario branch completed.');
    } catch (e) {
      writeLog(`Branch failed: ${e.message}`, null, true);
      byId('scenario-branch-summary').textContent = `Failed: ${e.message}`;
    }
  });

  byId('apply-scenario-overrides').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    let payload; try { payload = collectSettingsPayload(DIFF_SETTING_FIELDS, { includeNulls: false }); } catch (e) { writeLog(e.message, null, true); return; }
    if (!Object.keys(payload).length) { writeLog('Enter at least one override.', null, true); return; }
    writeLog(`Applying overrides...`, payload);
    try {
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/settings`, { method: 'PATCH', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
      renderDetail(); setSettingsInputs(DIFF_SETTING_FIELDS, {});
      byId('scenario-diff-summary').textContent = 'Overrides applied to plan settings.';
      await refreshPlans(); writeLog('Overrides applied.');
    } catch (e) { writeLog(`Apply failed: ${e.message}`, null, true); }
  });

  byId('activate-plan').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    try {
      const s = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/activate`, { method: 'POST' });
      await refreshPlans(); writeLog('Plan activated.', { id: s.id });
    } catch (e) { writeLog(`Activate failed: ${e.message}`, null, true); }
  });

  byId('refresh-plan-context').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    try {
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/refresh-context`, { method: 'POST' });
      renderDetail(); await refreshPlans(); writeLog('Context refreshed.');
    } catch (e) { writeLog(`Refresh failed: ${e.message}`, null, true); }
  });

  byId('add-decision').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    const sumEl = byId('decision-summary');
    const ratEl = byId('decision-rationale');
    const summary = sumEl.value.trim();
    if (!summary) { writeLog('Decision summary required.', null, true); return; }
    try {
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/decisions`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ summary, rationale: ratEl.value.trim(), status: byId('decision-status').value.trim() || 'proposed' }) });
      sumEl.value = ''; ratEl.value = '';
      renderDetail(); await refreshPlans(); writeLog('Decision added.');
    } catch (e) { writeLog(`Add decision failed: ${e.message}`, null, true); }
  });
}
