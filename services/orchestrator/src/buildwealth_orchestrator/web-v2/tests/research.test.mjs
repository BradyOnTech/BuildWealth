import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { renderEvidencePacket, renderResearchEmpty } from '../views/research.js';

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
  assert.match(apiSource, /\/api\/research\/evidence-packet/);
  assert.match(appSource, /views\/research\.js/);
  assert.match(appSource, /research/);
});
