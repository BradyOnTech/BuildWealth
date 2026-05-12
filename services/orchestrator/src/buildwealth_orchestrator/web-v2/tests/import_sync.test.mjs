import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { api } from '../lib/api.js';

test('import review page is native v2 copy without fallback handoff language', () => {
  const currentDir = dirname(fileURLToPath(import.meta.url));
  const source = readFileSync(resolve(currentDir, '../views/import_sync.js'), 'utf8');

  assert.match(source, /Import & Review/);
  assert.match(source, /Import workbench/);
  assert.match(source, /Preview import/);
  assert.match(source, /Apply ready rows/);
  assert.match(source, /Import reports/);
  assert.match(source, /Inbox review/);
  assert.match(source, /Sent to Inbox/);
  assert.match(source, /Resolve before apply/);
  assert.match(source, /Review in Investments & Assets/);
  assert.match(source, /Mapping confidence/);
  assert.match(source, /focusReportId/);
  assert.match(source, /Open saved import report/);
  assert.doesNotMatch(source, /classic/i);
  assert.doesNotMatch(source, /handoff/i);
});

test('v2 tools drawer does not expose external app bridge labels', () => {
  const currentDir = dirname(fileURLToPath(import.meta.url));
  const source = readFileSync(resolve(currentDir, '../app.js'), 'utf8');

  assert.doesNotMatch(source, /Ghostfolio/);
  assert.doesNotMatch(source, /Ignidash/);
  assert.doesNotMatch(source, /localhost:3333/);
  assert.doesNotMatch(source, /localhost:3000/);
  assert.doesNotMatch(source, /href:\s*'\/classic'/);
});

test('api import workbench helpers call native preview apply and report endpoints', async (t) => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return new Response(JSON.stringify({ ok: true, reports: [] }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  await api.importWorkbenchPreview(new FormData());
  await api.applyImportWorkbench('session 1', { archive_after_success: true });
  await api.importReports(7);
  await api.importReport('report 1');

  assert.equal(calls[0].url, '/api/import/workbench/preview');
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(calls[1].url, '/api/import/workbench/session%201/apply');
  assert.equal(calls[1].options.method, 'POST');
  assert.match(calls[1].options.body, /"archive_after_success":true/);
  assert.equal(calls[2].url, '/api/import/reports?limit=7');
  assert.equal(calls[3].url, '/api/import/reports/report%201');
});
