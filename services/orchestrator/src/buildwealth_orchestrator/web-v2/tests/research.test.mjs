import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import {
  normalizeCompareSymbols,
  renderCompareSurface,
  renderEvidencePacket,
  renderResearchEmpty,
} from '../views/research.js';

function packet(symbol, overrides = {}) {
  return {
    packet_id: `research-evidence:yfinance:${symbol}:6mo:1d`,
    symbol,
    name: `${symbol} Corp`,
    provider: 'yfinance',
    period: '6mo',
    interval: '1d',
    generated_at: '2026-04-28T12:00:00Z',
    coverage: {
      quote_available: true,
      history_available: true,
      provider_status: 'available',
      endpoints_attempted: ['quote', 'price_history'],
      warnings: [],
    },
    freshness: { status: 'fresh' },
    metrics: {
      last_price: 100,
      period_change_pct: 8,
      volatility_pct: 18,
    },
    risk: {
      drawdown_from_high_pct: -4,
    },
    quality: {
      confidence: 'high',
      coverage_score: 100,
      blocking_gaps: [],
    },
    provenance: { warnings: [] },
    ...overrides,
  };
}

test('research view renders a packet-native evidence summary', () => {
  const markup = String(renderEvidencePacket({
    packet_id: 'research-evidence:yfinance:NVDA:6mo:1d',
    symbol: 'NVDA',
    name: 'NVIDIA',
    provider: 'yfinance',
    period: '6mo',
    interval: '1d',
    generated_at: '2026-04-28T12:00:00Z',
    coverage: {
      quote_available: true,
      history_available: true,
      provider_status: 'available',
      endpoints_attempted: ['quote', 'price_history'],
      warnings: [],
    },
    freshness: {
      status: 'fresh',
      quote_as_of: '2026-04-28T11:55:00Z',
      history_as_of: '2026-04-27T20:00:00Z',
    },
    metrics: {
      last_price: 875.42,
      period_change_pct: 12.4,
      volatility_pct: 28.7,
      market_cap_usd: 2140000000000,
      pe_ratio: 61.2,
      dividend_yield_pct: 0.03,
    },
    risk: {
      drawdown_from_high_pct: -8.2,
    },
    quality: {
      confidence: 'high',
      coverage_score: 100,
      blocking_gaps: [],
    },
    provenance: {
      warnings: ['Provider response is normalized before display.'],
    },
  }));

  assert.match(markup, /Research evidence/);
  assert.match(markup, /NVDA/);
  assert.match(markup, /NVIDIA/);
  assert.match(markup, /yfinance/);
  assert.match(markup, /Fresh/);
  assert.match(markup, /High/);
  assert.match(markup, /100%/);
  assert.match(markup, /\$875\.42/);
  assert.match(markup, /\+12\.4%/);
  assert.match(markup, /28\.7%/);
  assert.match(markup, /\$2,140,000,000,000/);
  assert.match(markup, /quote/);
  assert.match(markup, /price history/);
  assert.match(markup, /research-evidence:yfinance:NVDA:6mo:1d/);
  assert.match(markup, /Provider response is normalized before display\./);
  assert.doesNotMatch(markup, /buy/i);
});

test('research view renders compare as packet cards plus ranking summary', () => {
  const markup = String(renderCompareSurface({
    provider: 'yfinance',
    period: '6mo',
    interval: '1d',
    generated_at: '2026-04-28T12:00:00Z',
    symbols: ['NVDA', 'MSFT', 'VTI'],
    summary: {
      requested_symbols: 3,
      compared_symbols: 3,
      available_symbols: 3,
      baseline_symbol: 'VTI',
      ranked_symbols: ['NVDA', 'MSFT', 'VTI'],
      best_period_return_symbol: 'NVDA',
      highest_volatility_symbol: 'NVDA',
      baseline_relative_return_pct: { NVDA: 12.4, MSFT: 4.2, VTI: 0 },
    },
    items: [
      {
        symbol: 'NVDA',
        rank: 1,
        score: 84,
        research_freshness_status: 'fresh',
        research_confidence: 'high',
        research_evidence_packet_id: 'research-evidence:yfinance:NVDA:6mo:1d',
      },
      {
        symbol: 'MSFT',
        rank: 2,
        score: 71,
        research_freshness_status: 'fresh',
        research_confidence: 'high',
        research_evidence_packet_id: 'research-evidence:yfinance:MSFT:6mo:1d',
      },
      {
        symbol: 'VTI',
        rank: 3,
        score: 58,
        research_freshness_status: 'fresh',
        research_confidence: 'high',
        research_evidence_packet_id: 'research-evidence:yfinance:VTI:6mo:1d',
      },
    ],
    warnings: ['NVDA: provider normalized quote response.'],
  }, [
    packet('NVDA', { metrics: { last_price: 875.42, period_change_pct: 12.4, volatility_pct: 28.7 } }),
    packet('MSFT', { metrics: { last_price: 410.18, period_change_pct: 4.2, volatility_pct: 19.1 } }),
    packet('VTI', { metrics: { last_price: 286.11, period_change_pct: 0, volatility_pct: 11.4 } }),
  ]));

  assert.match(markup, /Compare evidence/);
  assert.match(markup, /NVDA \/ MSFT \/ VTI/);
  assert.match(markup, /Baseline/);
  assert.match(markup, /VTI/);
  assert.match(markup, /Rank 1/);
  assert.match(markup, /Score 84/);
  assert.match(markup, /research-evidence:yfinance:NVDA:6mo:1d/);
  assert.match(markup, /research-evidence:yfinance:MSFT:6mo:1d/);
  assert.match(markup, /research-evidence:yfinance:VTI:6mo:1d/);
  assert.match(markup, /provider normalized quote response/i);
  assert.doesNotMatch(markup, /buy/i);
});

test('research compare normalizes and bounds symbols', () => {
  assert.deepEqual(
    normalizeCompareSymbols(' nvda, msft VTI nvda aapl goog '),
    ['NVDA', 'MSFT', 'VTI', 'AAPL'],
  );
});

test('research view renders an empty state without classic fallback copy', () => {
  const markup = String(renderResearchEmpty());

  assert.match(markup, /Research evidence/);
  assert.match(markup, /Inspect a symbol/);
  assert.doesNotMatch(markup, /classic/i);
});

test('research view and app wire packet endpoint and route', () => {
  const currentDir = dirname(fileURLToPath(import.meta.url));
  const apiSource = readFileSync(resolve(currentDir, '../lib/api.js'), 'utf8');
  const appSource = readFileSync(resolve(currentDir, '../app.js'), 'utf8');

  assert.match(apiSource, /researchEvidencePacket/);
  assert.match(apiSource, /researchCompare/);
  assert.match(apiSource, /\/api\/research\/evidence-packet/);
  assert.match(apiSource, /\/api\/research\/compare/);
  assert.match(appSource, /views\/research\.js/);
  assert.match(appSource, /research/);
});
