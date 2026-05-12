import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { dirname, extname, isAbsolute, join, relative, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';

import { test } from '@playwright/test';

const currentDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(currentDir, '..');

const CONTENT_TYPES = {
  '.css': 'text/css',
  '.html': 'text/html',
  '.js': 'text/javascript',
};

const jsonResponse = (body, status = 200) => ({
  status,
  contentType: 'application/json',
  body: JSON.stringify(body),
});

async function staticResponse(pathname) {
  const relativePath = pathname === '/' ? 'index.html' : pathname.replace(/^\/static-v2\//, '');
  const filePath = resolve(webRoot, relativePath);
  const distance = relative(webRoot, filePath);
  assert.ok(
    distance && !distance.startsWith('..') && !isAbsolute(distance),
    `refusing to serve path outside web root: ${pathname}`,
  );
  return {
    status: 200,
    contentType: CONTENT_TYPES[extname(filePath)] || 'text/plain',
    body: await readFile(filePath, 'utf8'),
  };
}

test('Import & Review previews unresolved assets, applies ready rows, and opens the saved report', async ({ page }) => {
  let applied = false;
  const reportId = 'ir-browser-1';
  const sessionId = 'imp-browser-1';
  const reviewItems = [
    {
      title: 'Asset needs review: row 3',
      detail: 'The row is missing an investment symbol, so BuildWealth cannot connect it to an asset.',
      action_payload: {
        kind: 'asset_review_item',
        session_id: sessionId,
        report_id: applied ? reportId : null,
        row_number: 3,
        review_route: {
          route: 'portfolio',
          label: 'Portfolio Assets',
          target: 'assets',
        },
      },
    },
  ];
  const reconciliationReport = {
    parser_confidence_flag: 'medium',
    parser_confidence_score: 0.72,
    accepted_count: 1,
    normalized_count: 0,
    rejected_count: 1,
    accepted_rows: [
      {
        row_number: 2,
        status: 'accepted',
        confidence_flag: 'high',
        normalized_row: { date: '2026-01-02', action: 'BUY', symbol: 'VTI', quantity: 2, unit_price: 250 },
      },
    ],
    rejected_rows: [
      {
        row_number: 3,
        status: 'rejected',
        confidence_flag: 'low',
        rejection_reasons: ['missing_symbol'],
        raw_row: { date: '2026-01-03', action: 'BUY' },
      },
    ],
  };
  const summary = {
    parsed_rows: 2,
    accepted_count: 1,
    normalized_count: 0,
    rejected_count: 1,
    duplicate_count: 0,
    unresolved_count: 1,
    asset_review_count: 1,
    account_review_count: 0,
    review_item_count: 1,
    parser_confidence_flag: 'medium',
    parser_confidence_score: 0.72,
    warnings_count: 0,
    errors_count: 1,
  };
  const preview = () => ({
    schema_version: 1,
    session_id: sessionId,
    created_at: '2026-05-12T12:00:00Z',
    updated_at: '2026-05-12T12:00:00Z',
    status: applied ? 'applied' : 'previewed',
    source_file: { path: '/tmp/browser.csv', name: 'browser.csv', stored_name: 'browser.csv', size_bytes: 64 },
    options: {},
    summary,
    report_id: applied ? reportId : null,
    review_items: reviewItems,
    preview_response: {
      file_path: '/tmp/browser.csv',
      dry_run: !applied,
      selected_template: 'auto',
      detected_template: 'schwab',
      parsed_rows: 2,
      valid_activities: 1,
      imported_activities: applied ? 1 : 0,
      warnings: [],
      errors: ['Row 3: Missing symbol/ticker.'],
      reconciliation_report: reconciliationReport,
    },
  });
  const report = () => ({
    ...preview(),
    report_id: reportId,
    operator: 'user',
    imported_activities: 1,
    selected_template: 'auto',
    detected_template: 'schwab',
    warnings: [],
    errors: ['Row 3: Missing symbol/ticker.'],
    reconciliation_report: reconciliationReport,
    affected_links: {
      import_report: `#import-sync?report=${reportId}`,
      portfolio_history: `#portfolio?section=transactions&import_report=${reportId}`,
      portfolio_assets: '#portfolio?section=assets',
    },
    review_items: reviewItems.map(item => ({
      ...item,
      action_payload: { ...item.action_payload, report_id: reportId },
    })),
  });

  await page.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());

    if (url.hostname !== 'buildwealth-v2.test') {
      await route.abort();
      return;
    }

    if (url.pathname === '/' || url.pathname.startsWith('/static-v2/')) {
      await route.fulfill(await staticResponse(url.pathname));
      return;
    }

    if (url.pathname === '/api/plans') {
      await route.fulfill(jsonResponse([{ id: 'plan-1', title: 'Primary Plan', is_active: true }]));
      return;
    }

    if (url.pathname === '/api/import/workbench/preview' && request.method() === 'POST') {
      await route.fulfill(jsonResponse(preview()));
      return;
    }

    if (url.pathname === `/api/import/workbench/${sessionId}/apply` && request.method() === 'POST') {
      applied = true;
      await route.fulfill(jsonResponse({ session: preview(), report: report() }));
      return;
    }

    if (url.pathname === '/api/import/reports') {
      await route.fulfill(jsonResponse({ reports: applied ? [report()] : [] }));
      return;
    }

    if (url.pathname === `/api/import/reports/${reportId}`) {
      await route.fulfill(jsonResponse(report()));
      return;
    }

    if (url.pathname === '/api/sync/status') {
      await route.fulfill(jsonResponse({ running: false, runs_total: 0, runs_failed: 0 }));
      return;
    }

    if (url.pathname === '/api/import/files') {
      await route.fulfill(jsonResponse({ items: [] }));
      return;
    }

    if (url.pathname === '/api/import/csv-templates') {
      await route.fulfill(jsonResponse({
        templates: [
          {
            id: 'auto',
            name: 'Auto Detect',
            description: 'Detect broker format from CSV headers.',
            required_columns: [],
            optional_columns: [],
            mapping_confidence: 'auto',
          },
          {
            id: 'schwab',
            name: 'Charles Schwab',
            description: 'Schwab transactions export.',
            required_columns: ['date', 'action', 'symbol', 'quantity', 'price'],
            optional_columns: ['amount', 'fees&comm'],
            mapping_confidence: 'known',
          },
        ],
      }));
      return;
    }

    await route.fulfill(jsonResponse({}));
  });

  const dir = await mkdtemp(join(tmpdir(), 'buildwealth-import-'));
  const filePath = join(dir, 'browser.csv');
  await writeFile(filePath, 'date,action,symbol,quantity,price\n2026-01-02,BUY,VTI,2,250\n2026-01-03,BUY,,1,20\n', 'utf8');

  await page.goto('http://buildwealth-v2.test/#import-sync');
  await page.setInputFiles('input[type="file"]', filePath);
  await page.getByRole('button', { name: 'Preview import' }).click();

  await page.getByText('Resolve before apply').waitFor({ state: 'visible' });
  await page.getByText('Review in Investments & Assets').waitFor({ state: 'visible' });
  await page.getByText('Medium confidence').first().waitFor({ state: 'visible' });

  await page.getByRole('button', { name: 'Apply ready rows' }).click();
  await page.getByText('Import applied').waitFor({ state: 'visible' });
  await page.getByText('Open saved import report').click();
  await page.getByText('Source evidence').waitFor({ state: 'visible' });
  await page.getByText('Sent to Inbox').waitFor({ state: 'visible' });
  await page.getByRole('link', { name: /portfolio history/i }).waitFor({ state: 'visible' });
});
