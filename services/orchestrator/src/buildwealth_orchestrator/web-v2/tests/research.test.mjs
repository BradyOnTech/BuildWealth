import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import {
  normalizeCompareSymbols,
  renderDossierDetail,
  renderDossierLookupSurface,
  renderCompareSurface,
  renderEvidencePacket,
  renderResearchEmpty,
  renderThesisReviewSurface,
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

test('research view renders saved dossier lookup rows', () => {
  const markup = String(renderDossierLookupSurface({
    plan_id: 'plan-1',
    count: 1,
    items: [
      {
        artifact_id: 'artifact-dossier',
        file_name: '2026-research-dossier-nvda-msft.md',
        title: 'Research Dossier - NVDA vs MSFT',
        created_at: '2026-04-28T12:00:00Z',
        plan_id: 'plan-1',
        symbols: ['NVDA', 'MSFT'],
        thesis_review: {
          status: 'expired',
          age_days: 42,
          stale_after_days: 30,
          reviewed_at: '2026-03-17T12:00:00Z',
          expires_at: '2026-04-16T12:00:00Z',
        },
        content_preview: '## Evidence Packets\n\n| Symbol | Packet | Provider | Freshness | Confidence | Coverage | Blocking gaps |\n| --- | --- | --- | --- | --- | ---: | --- |\n| NVDA | research-evidence:yfinance:NVDA:6mo:1d | yfinance | fresh | high | 100% | none |',
      },
    ],
    warnings: [],
  }));

  assert.match(markup, /Research dossiers/);
  assert.match(markup, /Research Dossier - NVDA vs MSFT/);
  assert.match(markup, /NVDA · MSFT/);
  assert.match(markup, /Review due/);
  assert.match(markup, /42 days old/);
  assert.match(markup, /1 packet citation/);
  assert.match(markup, /href="#research\?dossier=artifact-dossier&amp;plan=plan-1"/);
  assert.doesNotMatch(markup, /classic/i);
});

test('research view renders dossier detail with packet citation links', () => {
  const markup = String(renderDossierDetail({
    id: 'artifact-dossier',
    file_name: '2026-research-dossier-nvda-msft.md',
    title: 'Research Dossier - NVDA vs MSFT',
    created_at: '2026-04-28T12:00:00Z',
    thesis_review: {
      status: 'current',
      age_days: 4,
      stale_after_days: 30,
      reviewed_at: '2026-04-24T12:00:00Z',
      expires_at: '2026-05-24T12:00:00Z',
    },
    content: [
      '# Research Dossier: NVDA vs MSFT',
      '',
      '## Thesis',
      '',
      'Compare AI infrastructure exposure.',
      '',
      '## Evidence Packets',
      '',
      '| Symbol | Packet | Provider | Freshness | Confidence | Coverage | Blocking gaps |',
      '| --- | --- | --- | --- | --- | ---: | --- |',
      '| NVDA | research-evidence:yfinance:NVDA:6mo:1d | yfinance | fresh | high | 100% | none |',
      '| MSFT | research-evidence:yfinance:MSFT:6mo:1d | yfinance | fresh | high | 100% | none |',
    ].join('\n'),
  }, { planId: 'plan-1' }));

  assert.match(markup, /Dossier detail/);
  assert.match(markup, /Research Dossier - NVDA vs MSFT/);
  assert.match(markup, /Thesis current/);
  assert.match(markup, /Expires/);
  assert.match(markup, /Packet citations/);
  assert.match(markup, /research-evidence:yfinance:NVDA:6mo:1d/);
  assert.match(markup, /href="#research\?symbol=NVDA&amp;packet=research-evidence%3Ayfinance%3ANVDA%3A6mo%3A1d"/);
  assert.match(markup, /href="#research\?compare=NVDA%2CMSFT"/);
  assert.match(markup, /Compare AI infrastructure exposure\./);
  assert.doesNotMatch(markup, /buy/i);
});

test('research view renders a dedicated thesis review surface', () => {
  const markup = String(renderThesisReviewSurface({
    artifact: {
      id: 'artifact-dossier-msft',
      title: 'Research Dossier - MSFT vs VTI',
      created_at: '2026-03-17T12:00:00Z',
      thesis_review: {
        status: 'expired',
        age_days: 42,
        stale_after_days: 30,
        reviewed_at: '2026-03-17T12:00:00Z',
        expires_at: '2026-04-16T12:00:00Z',
        reference_price_usd: 410,
      },
      content: [
        '# Research Dossier: MSFT vs VTI',
        '',
        '## Thesis',
        '',
        'Compare durable software cash flow against broad market exposure.',
        '',
        '## Evidence Packets',
        '',
        '| Symbol | Packet | Provider | Freshness | Confidence | Coverage | Blocking gaps |',
        '| --- | --- | --- | --- | --- | ---: | --- |',
        '| MSFT | research-evidence:yfinance:MSFT:6mo:1d | yfinance | stale | medium | 82% | none |',
        '| VTI | research-evidence:yfinance:VTI:6mo:1d | yfinance | fresh | high | 96% | none |',
      ].join('\n'),
    },
    recommendation: {
      id: 'rec-thesis-expired',
      title: 'Refresh stale research thesis for MSFT / VTI',
      detail: 'The saved research thesis is past the review window.',
      plan_id: 'plan-1',
      action_payload: {
        evidence: {
          symbols: ['MSFT', 'VTI'],
          freshness_status: 'stale',
          reference_price_usd: 410,
          material_price_change_pct: 12.2,
          packet_citations: ['research-evidence:yfinance:MSFT:6mo:1d'],
        },
      },
    },
    packet: packet('MSFT', {
      metrics: { last_price: 460.02, period_change_pct: 10.8, volatility_pct: 19.1 },
      freshness: { status: 'stale' },
      quality: { confidence: 'medium', coverage_score: 82, blocking_gaps: [] },
    }),
    planId: 'plan-1',
  }));

  assert.match(markup, /Thesis review/);
  assert.match(markup, /Refresh stale research thesis for MSFT \/ VTI/);
  assert.match(markup, /Review due/);
  assert.match(markup, /Reference price/);
  assert.match(markup, /\$410\.00/);
  assert.match(markup, /Current price/);
  assert.match(markup, /\$460\.02/);
  assert.match(markup, /Material move/);
  assert.match(markup, /\+12\.2%/);
  assert.match(markup, /Packet citations/);
  assert.match(markup, /research-evidence:yfinance:MSFT:6mo:1d/);
  assert.match(markup, /href="#research\?symbol=MSFT&amp;packet=research-evidence%3Ayfinance%3AMSFT%3A6mo%3A1d"/);
  assert.match(markup, /Mark thesis reviewed/);
  assert.match(markup, /Revise in Copilot/);
  assert.match(markup, /href="#research\?dossier=artifact-dossier-msft&amp;plan=plan-1"/);
  assert.match(markup, /href="#research\?compare=MSFT%2CVTI"/);
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
  assert.match(apiSource, /researchCompare/);
  assert.match(apiSource, /researchDossiers/);
  assert.match(apiSource, /planArtifact/);
  assert.match(apiSource, /\/api\/research\/evidence-packet/);
  assert.match(apiSource, /\/api\/research\/compare/);
  assert.match(apiSource, /\/api\/research\/dossiers/);
  assert.match(apiSource, /\/api\/plans\/.*artifacts/);
  assert.match(appSource, /views\/research\.js/);
  assert.match(appSource, /research/);
});
