import { fetchJson } from '../lib/api.js';
import { state } from '../lib/state.js';
import { byId, fmtCurrency, fmtPct, fmtDate, writeLog } from '../lib/utils.js';

export const id = 'research';
export const label = 'Research';
export const icon = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="9" cy="9" r="5.5"/><line x1="13" y1="13" x2="17" y2="17"/></svg>';

const DEFAULT_SYMBOLS = 'AAPL, MSFT, VTI';
const DEFAULT_PERIOD = '6mo';
const DEFAULT_INTERVAL = '1d';
const DEFAULT_THESIS = '';

function parseSymbols(raw) {
  const seen = new Set();
  const symbols = [];
  for (const chunk of String(raw || '').split(',')) {
    const symbol = chunk.trim().toUpperCase().replace(/[^A-Z0-9._-]+/g, '');
    if (!symbol || seen.has(symbol)) continue;
    seen.add(symbol);
    symbols.push(symbol);
    if (symbols.length >= 20) break;
  }
  return symbols;
}

function parseTextList(raw) {
  const seen = new Set();
  const values = [];
  const normalized = String(raw || '').replace(/\n/g, ',');
  for (const chunk of normalized.split(',')) {
    const value = chunk.trim();
    if (!value) continue;
    const lowered = value.toLowerCase();
    if (seen.has(lowered)) continue;
    seen.add(lowered);
    values.push(value);
    if (values.length >= 12) break;
  }
  return values;
}

function fmtMaybeCurrency(value) {
  return typeof value === 'number' && Number.isFinite(value) ? fmtCurrency(value) : '-';
}

function fmtMaybePct(value) {
  return typeof value === 'number' && Number.isFinite(value) ? fmtPct(value) : '-';
}

function fmtMaybeNumber(value, digits = 2) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '-';
}

export function template() {
  return `
    <div class="view-header">
      <h2>Research Intelligence</h2>
      <div class="header-actions">
        <button class="ghost small" id="research-reset">Reset</button>
        <button class="ghost small" id="research-run-dossier">Generate Dossier</button>
        <button class="primary small" id="research-run-compare">Run Compare</button>
      </div>
    </div>
    <p class="hint">Compare symbols, then package thesis evidence into a reusable research dossier artifact.</p>

    <form id="research-compare-form" class="txn-form">
      <label class="field"><span>Symbols</span><input id="research-symbols" type="text" value="${DEFAULT_SYMBOLS}" placeholder="AAPL, MSFT, VTI" required /></label>
      <label class="field"><span>Baseline Symbol (optional)</span><input id="research-baseline-symbol" type="text" placeholder="AAPL" /></label>
      <label class="field"><span>Period</span>
        <select id="research-period">
          <option value="1mo">1mo</option>
          <option value="3mo">3mo</option>
          <option value="6mo" selected>6mo</option>
          <option value="1y">1y</option>
          <option value="2y">2y</option>
          <option value="5y">5y</option>
        </select>
      </label>
      <label class="field"><span>Interval</span>
        <select id="research-interval">
          <option value="1d" selected>1d</option>
          <option value="1wk">1wk</option>
          <option value="1mo">1mo</option>
        </select>
      </label>
      <button class="primary" type="submit">Run Compare</button>
    </form>

    <p class="hint" id="research-compare-summary">Run a comparison to view ranked symbols.</p>
    <div class="table-wrap"><table>
      <thead>
        <tr>
          <th>Rank</th>
          <th>Symbol</th>
          <th>Last Price</th>
          <th>Day</th>
          <th>Period</th>
          <th>Volatility</th>
          <th>P/E</th>
          <th>Dividend Yield</th>
          <th>Market Cap</th>
          <th>Score</th>
        </tr>
      </thead>
      <tbody id="research-compare-body"><tr><td colspan="10">No comparison run yet.</td></tr></tbody>
    </table></div>

    <p class="hint" id="research-compare-meta"></p>
    <div id="research-compare-warnings" class="item-list"></div>

    <hr />

    <form id="research-dossier-form" class="txn-form">
      <label class="field"><span>Thesis</span><textarea id="research-dossier-thesis" rows="3" placeholder="Core investment thesis.">${DEFAULT_THESIS}</textarea></label>
      <label class="field"><span>Risks (comma-separated)</span><input id="research-dossier-risks" type="text" placeholder="valuation, regulation, demand slowdown" /></label>
      <label class="field"><span>Catalysts (comma-separated)</span><input id="research-dossier-catalysts" type="text" placeholder="earnings beat, margin expansion" /></label>
      <label class="field"><span>Plan ID (optional)</span><input id="research-dossier-plan-id" type="text" placeholder="plan-..." /></label>
      <label class="inline-check"><input type="checkbox" id="research-dossier-save" checked /> Save dossier to plan artifacts</label>
      <label class="inline-check"><input type="checkbox" id="research-dossier-fit" checked /> Include portfolio-fit analysis</label>
      <button class="primary" type="submit">Generate Dossier</button>
    </form>

    <p class="hint" id="research-dossier-summary">Generate a dossier after setting thesis and risk assumptions.</p>
    <div id="research-dossier-takeaways" class="item-list"></div>
    <p class="hint" id="research-dossier-artifact"></p>
    <pre id="research-dossier-markdown"></pre>
    <div id="research-dossier-warnings" class="item-list"></div>
  `;
}

function renderWarnings(warnings, targetId = 'research-compare-warnings') {
  const list = byId(targetId);
  const rows = Array.isArray(warnings) ? warnings : [];
  if (!rows.length) {
    list.innerHTML = '';
    return;
  }
  list.innerHTML = rows.map((warning) => (
    `<article class="list-item attention"><p class="list-item-title">Warning</p><p class="list-item-meta">${warning}</p></article>`
  )).join('');
}

function renderResult(payload) {
  state.researchCompare = payload;
  const summary = payload && typeof payload.summary === 'object' ? payload.summary : {};
  const items = Array.isArray(payload?.items) ? payload.items : [];
  const best = summary.best_period_return_symbol || 'n/a';
  const worst = summary.worst_period_return_symbol || 'n/a';
  const baseline = summary.baseline_symbol || 'n/a';
  const available = Number(summary.available_symbols || 0);
  const compared = Number(summary.compared_symbols || items.length);

  byId('research-compare-summary').textContent =
    `Compared ${available}/${compared} symbols • best period return ${best} • worst ${worst} • baseline ${baseline}.`;

  const generatedAt = payload?.generated_at ? fmtDate(payload.generated_at) : '-';
  byId('research-compare-meta').textContent =
    `Provider ${payload?.provider || '-'} • ${payload?.period || '-'} @ ${payload?.interval || '-'} • Generated ${generatedAt}`;

  const body = byId('research-compare-body');
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="10">No symbols available for comparison.</td></tr>';
    renderWarnings(payload?.warnings || []);
    return;
  }

  body.innerHTML = items.map((item) => {
    const rank = item.rank ?? '-';
    const symbol = item.symbol || '-';
    return `
      <tr>
        <td>${rank}</td>
        <td>${symbol}</td>
        <td>${fmtMaybeCurrency(item.last_price)}</td>
        <td>${fmtMaybePct(item.day_change_pct)}</td>
        <td>${fmtMaybePct(item.period_change_pct)}</td>
        <td>${fmtMaybePct(item.volatility_pct)}</td>
        <td>${fmtMaybeNumber(item.pe_ratio)}</td>
        <td>${fmtMaybePct(item.dividend_yield_pct)}</td>
        <td>${fmtMaybeCurrency(item.market_cap_usd)}</td>
        <td>${fmtMaybeNumber(item.score, 3)}</td>
      </tr>`;
  }).join('');

  renderWarnings(payload?.warnings || []);
}

function renderDossier(payload) {
  state.researchDossier = payload;
  const freshness = payload && typeof payload.freshness === 'object' ? payload.freshness : {};
  const status = freshness.status || 'unknown';
  const available = Number(freshness.available_symbols || 0);
  const compared = Number(freshness.compared_symbols || 0);

  byId('research-dossier-summary').textContent =
    `${payload?.headline || 'Research dossier generated.'} Freshness: ${status} (${available}/${compared} symbols).`;

  const takeaways = Array.isArray(payload?.key_takeaways) ? payload.key_takeaways : [];
  const takeawaysList = byId('research-dossier-takeaways');
  if (!takeaways.length) {
    takeawaysList.innerHTML = '<article class="list-item"><p class="list-item-title">No key takeaways.</p></article>';
  } else {
    takeawaysList.innerHTML = takeaways.map((item) => (
      `<article class="list-item"><p class="list-item-title">Takeaway</p><p class="list-item-meta">${item}</p></article>`
    )).join('');
  }

  const artifact = payload?.artifact && typeof payload.artifact === 'object' ? payload.artifact : null;
  if (artifact?.id) {
    byId('research-dossier-artifact').textContent = `Saved as plan artifact: ${artifact.title || artifact.id} (${artifact.file_name || 'markdown'}).`;
  } else {
    byId('research-dossier-artifact').textContent = 'No plan artifact saved for this dossier run.';
  }

  byId('research-dossier-markdown').textContent = String(payload?.dossier_markdown || '').trim();
  renderWarnings(payload?.warnings || [], 'research-dossier-warnings');
}

async function runCompare() {
  const symbols = parseSymbols(byId('research-symbols').value);
  const period = String(byId('research-period').value || DEFAULT_PERIOD);
  const interval = String(byId('research-interval').value || DEFAULT_INTERVAL);
  const baselineSymbol = String(byId('research-baseline-symbol').value || '').trim().toUpperCase();

  if (symbols.length < 2) {
    writeLog('Research compare needs at least two symbols.', { symbols }, true);
    byId('research-compare-summary').textContent = 'Please enter at least two symbols.';
    return;
  }

  const payload = {
    symbols,
    period,
    interval,
  };
  if (baselineSymbol) payload.baseline_symbol = baselineSymbol;

  const button = byId('research-run-compare');
  button.disabled = true;
  button.textContent = 'Running...';
  byId('research-compare-summary').textContent = 'Running comparison...';
  writeLog('Running research compare...', payload);
  try {
    const result = await fetchJson('/api/research/compare', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    renderResult(result);
    writeLog('Research compare completed.', {
      symbols: result.symbols,
      best_period_return_symbol: result?.summary?.best_period_return_symbol,
      warnings: Array.isArray(result.warnings) ? result.warnings.length : 0,
    });
  } catch (error) {
    writeLog(`Research compare failed: ${error.message}`, null, true);
    byId('research-compare-summary').textContent = `Compare failed: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = 'Run Compare';
  }
}

async function runDossier() {
  const symbols = parseSymbols(byId('research-symbols').value);
  const period = String(byId('research-period').value || DEFAULT_PERIOD);
  const interval = String(byId('research-interval').value || DEFAULT_INTERVAL);
  const baselineSymbol = String(byId('research-baseline-symbol').value || '').trim().toUpperCase();
  const thesis = String(byId('research-dossier-thesis').value || '').trim();
  const risks = parseTextList(byId('research-dossier-risks').value);
  const catalysts = parseTextList(byId('research-dossier-catalysts').value);
  const planId = String(byId('research-dossier-plan-id').value || '').trim();
  const saveToPlan = Boolean(byId('research-dossier-save').checked);
  const includePortfolioFit = Boolean(byId('research-dossier-fit').checked);

  if (symbols.length < 2) {
    writeLog('Research dossier needs at least two symbols.', { symbols }, true);
    byId('research-dossier-summary').textContent = 'Please enter at least two symbols before generating a dossier.';
    return;
  }

  const payload = {
    symbols,
    period,
    interval,
    thesis,
    risks,
    catalysts,
    save_to_plan: saveToPlan,
    include_portfolio_fit: includePortfolioFit,
  };
  if (baselineSymbol) payload.baseline_symbol = baselineSymbol;
  if (planId) payload.plan_id = planId;

  const button = byId('research-run-dossier');
  button.disabled = true;
  button.textContent = 'Generating...';
  byId('research-dossier-summary').textContent = 'Generating dossier...';
  writeLog('Running research dossier generation...', payload);

  try {
    const result = await fetchJson('/api/research/dossier', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    renderDossier(result);
    writeLog('Research dossier completed.', {
      symbols: result.symbols,
      freshness_status: result?.freshness?.status,
      saved: Boolean(result?.artifact?.id),
      warnings: Array.isArray(result.warnings) ? result.warnings.length : 0,
    });
  } catch (error) {
    writeLog(`Research dossier failed: ${error.message}`, null, true);
    byId('research-dossier-summary').textContent = `Dossier failed: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = 'Generate Dossier';
  }
}

function resetForm() {
  byId('research-symbols').value = DEFAULT_SYMBOLS;
  byId('research-baseline-symbol').value = '';
  byId('research-period').value = DEFAULT_PERIOD;
  byId('research-interval').value = DEFAULT_INTERVAL;

  byId('research-compare-summary').textContent = 'Run a comparison to view ranked symbols.';
  byId('research-compare-meta').textContent = '';
  byId('research-compare-body').innerHTML = '<tr><td colspan="10">No comparison run yet.</td></tr>';
  byId('research-compare-warnings').innerHTML = '';

  byId('research-dossier-thesis').value = DEFAULT_THESIS;
  byId('research-dossier-risks').value = '';
  byId('research-dossier-catalysts').value = '';
  byId('research-dossier-plan-id').value = '';
  byId('research-dossier-save').checked = true;
  byId('research-dossier-fit').checked = true;
  byId('research-dossier-summary').textContent = 'Generate a dossier after setting thesis and risk assumptions.';
  byId('research-dossier-takeaways').innerHTML = '';
  byId('research-dossier-artifact').textContent = '';
  byId('research-dossier-markdown').textContent = '';
  byId('research-dossier-warnings').innerHTML = '';
}

export function init() {
  byId('research-compare-form').addEventListener('submit', (event) => {
    event.preventDefault();
    runCompare();
  });
  byId('research-run-compare').addEventListener('click', () => {
    runCompare();
  });
  byId('research-dossier-form').addEventListener('submit', (event) => {
    event.preventDefault();
    runDossier();
  });
  byId('research-run-dossier').addEventListener('click', () => {
    runDossier();
  });
  byId('research-reset').addEventListener('click', () => {
    resetForm();
  });

  resetForm();
  if (state.researchCompare) {
    renderResult(state.researchCompare);
  }
  if (state.researchDossier) {
    renderDossier(state.researchDossier);
  }
}
