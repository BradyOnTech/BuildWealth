import test from 'node:test';
import assert from 'node:assert/strict';

const storage = new Map();
globalThis.window = globalThis.window || {
  sessionStorage: {
    getItem: key => storage.get(key) || '',
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: key => storage.delete(key),
  },
};

const { renderMorningBrief } = await import('../views/today.js');

const BRIEF = {
  generated_at: '2026-07-12T09:00:00Z',
  since: '2026-07-09T08:00:00Z',
  first_visit: false,
  has_news: true,
  new_recommendations: {
    count: 2,
    items: [{ id: 'rec-1', title: 'Trim NVDA back under policy', priority: 'high' }],
  },
  risk_alerts: {
    status: 'breach',
    breach_count: 1,
    watch_count: 0,
    items: [{ severity: 'high', kind: 'single_symbol_exposure', message: 'NVDA is 18% of the portfolio.' }],
  },
  pending_context_reviews: { count: 1 },
  portfolio: { available: true, total_value_usd: 104000, change_since_seen_usd: 4000, change_since_seen_pct: 4 },
};

test('renderMorningBrief shows digest rows, drift, and caught-up control', () => {
  const markup = String(renderMorningBrief(BRIEF));
  assert.match(markup, /Since you last looked/);
  assert.match(markup, /2 new suggestions/);
  assert.match(markup, /Trim NVDA back under policy/);
  assert.match(markup, /1 risk breach/);
  assert.match(markup, /1 context capture/);
  assert.match(markup, /Portfolio up \$4,000 since then/);
  assert.match(markup, /data-action="brief-caught-up"/);
  assert.match(markup, /#inbox/);
});

test('renderMorningBrief stays quiet on first visit or no news', () => {
  assert.equal(String(renderMorningBrief(null)), '');
  assert.equal(String(renderMorningBrief({ ...BRIEF, first_visit: true })), '');
  assert.equal(String(renderMorningBrief({ ...BRIEF, has_news: false })), '');
});
