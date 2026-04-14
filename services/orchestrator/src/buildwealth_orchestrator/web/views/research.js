import { fetchJson } from '../lib/api.js';
import { state } from '../lib/state.js';
import { byId, fmtCurrency, fmtPct, fmtDate, writeLog } from '../lib/utils.js';

export const id = 'research';
export const label = 'Research';
export const icon = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="9" cy="9" r="5.5"/><line x1="13" y1="13" x2="17" y2="17"/></svg>';

const DEFAULT_SYMBOLS = 'AAPL, MSFT, VTI';
const DEFAULT_PERIOD = '6mo';
const DEFAULT_INTERVAL = '1d';

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
      <h2>Research Compare</h2>
      <div class="header-actions">
        <button class="ghost small" id="research-reset">Reset</button>
        <button class="primary small" id="research-run-compare">Run Compare</button>
      </div>
    </div>
    <p class="hint">Compare multiple symbols with normalized return/volatility context before simulating portfolio impact.</p>

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
  `;
}

function renderWarnings(warnings) {
  const list = byId('research-compare-warnings');
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

function resetForm() {
  byId('research-symbols').value = DEFAULT_SYMBOLS;
  byId('research-baseline-symbol').value = '';
  byId('research-period').value = DEFAULT_PERIOD;
  byId('research-interval').value = DEFAULT_INTERVAL;
  byId('research-compare-summary').textContent = 'Run a comparison to view ranked symbols.';
  byId('research-compare-meta').textContent = '';
  byId('research-compare-body').innerHTML = '<tr><td colspan="10">No comparison run yet.</td></tr>';
  byId('research-compare-warnings').innerHTML = '';
}

export function init() {
  byId('research-compare-form').addEventListener('submit', (event) => {
    event.preventDefault();
    runCompare();
  });
  byId('research-run-compare').addEventListener('click', () => {
    runCompare();
  });
  byId('research-reset').addEventListener('click', () => {
    resetForm();
  });

  if (state.researchCompare) {
    renderResult(state.researchCompare);
  } else {
    resetForm();
  }
}
