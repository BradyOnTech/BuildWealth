import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, extname, isAbsolute, relative, resolve } from 'node:path';
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

test('Atelier surfaces trust durability state in v2', async ({ page }) => {
  let backupCreated = false;
  let protectionApplied = false;
  let checkpointCreated = false;
  let restorePreviewRequested = false;

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

    if (url.pathname === '/api/storage/durable/status') {
      await route.fulfill(jsonResponse({
        database_exists: true,
        document_count: 12,
        latest_rollback_check_passed: true,
        latest_migration_at: '2026-04-30T12:00:00Z',
      }));
      return;
    }

    if (url.pathname === '/api/storage/backups') {
      if (request.method() === 'POST') {
        backupCreated = true;
        await route.fulfill(jsonResponse({
          backup_id: 'backup-new',
          created_at: '2026-04-30T12:05:00Z',
          archive_size_bytes: 4096,
          files_backed_up: 10,
          total_bytes: 2048,
        }));
        return;
      }
      await route.fulfill(jsonResponse({
        backups: [{
          backup_id: backupCreated ? 'backup-new' : '20260430T120000Z',
          created_at: '2026-04-30T12:00:00Z',
          size_bytes: 2048,
        }],
      }));
      return;
    }

    if (url.pathname === '/api/storage/protection/status') {
      await route.fulfill(jsonResponse({
        supported: true,
        total_non_compliant_files: protectionApplied ? 0 : 2,
        total_non_compliant_directories: protectionApplied ? 0 : 1,
        policy: { protection_level: 'standard', last_applied_at: null },
      }));
      return;
    }

    if (url.pathname === '/api/storage/protection/apply' && request.method() === 'POST') {
      protectionApplied = true;
      await route.fulfill(jsonResponse({
        applied_at: '2026-04-30T12:06:00Z',
        supported: true,
        protection_level: 'standard',
        include_backups: false,
        files_scanned: 10,
        directories_scanned: 3,
        files_updated: 2,
        directories_updated: 1,
        non_compliant_files_after: 0,
        non_compliant_directories_after: 0,
        warnings: [],
      }));
      return;
    }

    if (url.pathname === '/api/git/status') {
      await route.fulfill(jsonResponse({
        status: 'ok',
        dirty: !checkpointCreated,
        changed_files: checkpointCreated ? [] : [{ path: 'plans/plan.md', status: 'M' }],
        last_commit: {
          hash: 'abc123',
          short_hash: 'abc123',
          date: '2026-04-30T12:00:00Z',
          message: 'Previous checkpoint',
        },
        has_remote: false,
      }));
      return;
    }

    if (url.pathname === '/api/git/checkpoint' && request.method() === 'POST') {
      checkpointCreated = true;
      await route.fulfill(jsonResponse({
        status: 'committed',
        message: 'Checkpoint created.',
        workspace_dir: '/tmp/buildwealth-versioned',
        files_written: 1,
        files_removed: 0,
        sections: {},
        commit: {
          hash: 'def456',
          short_hash: 'def456',
          date: '2026-04-30T12:07:00Z',
          message: 'BuildWealth v2 trust checkpoint',
        },
      }));
      return;
    }

    if (url.pathname === '/api/git/restore-preview') {
      restorePreviewRequested = url.searchParams.get('ref') === 'abc123';
      await route.fulfill(jsonResponse({
        status: 'ok',
        message: 'Read-only restore preview generated. No files were changed.',
        workspace_dir: '/tmp/buildwealth-versioned',
        ref: 'abc123',
        read_only: true,
        total_files: 1,
        warnings: ['Preview only.'],
        files: [{
          path: 'plans/plan.md',
          status: 'modified',
          diff: '- old\n+ new',
          truncated: false,
        }],
      }));
      return;
    }

    if (url.pathname === '/api/git/activity') {
      await route.fulfill(jsonResponse({
        summary: { total_matched: 3 },
        events: [
          {
            id: 'audit-profile',
            created_at: '2026-04-30T12:00:00Z',
            event_type: 'profile_update',
            title: 'Financial profile updated',
            message: 'Updated profile sections: tax profile.',
            status: 'applied',
            metadata: { sections: ['tax_profile'], source: 'profile_editor' },
          },
          {
            id: 'audit-copilot',
            created_at: '2026-04-30T12:03:00Z',
            event_type: 'copilot_recommendation_apply',
            title: 'Copilot applied recommendation',
            message: 'Recommendation applied.',
            status: 'applied',
            metadata: { recommendation_id: 'rec-123', source: 'copilot_tool' },
          },
          {
            id: 'audit-preview',
            created_at: '2026-04-30T12:04:00Z',
            event_type: 'restore_preview',
            title: 'Restore preview generated',
            message: 'Preview only.',
            status: 'ok',
            metadata: {},
          },
        ],
      }));
      return;
    }

    await route.fulfill(jsonResponse({}));
  });

  await page.goto('http://buildwealth-v2.test/#atelier');
  await page.getByRole('heading', { name: 'Trust & durability' }).waitFor({ state: 'visible' });
  await page.getByText('Needs review').first().waitFor({ state: 'visible' });
  await page.getByText('20260430T120000Z', { exact: true }).waitFor({ state: 'visible' });
  await page.getByText('3 issues', { exact: true }).waitFor({ state: 'visible' });
  await page.getByText('1 uncheckpointed', { exact: true }).waitFor({ state: 'visible' });
  await page.getByRole('heading', { name: 'Ready to rely today?' }).waitFor({ state: 'visible' });
  await page.getByText('Backup available').waitFor({ state: 'visible' });
  await page.getByText('Restore preview verified').waitFor({ state: 'visible' });
  await page.getByRole('heading', { name: 'Profile & Copilot changes' }).waitFor({ state: 'visible' });
  await page.getByText('Financial profile updated').waitFor({ state: 'visible' });
  await page.getByText('Copilot applied recommendation').waitFor({ state: 'visible' });
  await page.getByRole('link', { name: 'Open classic storage tools' }).waitFor({ state: 'visible' });

  await page.getByRole('button', { name: 'Create backup' }).click();
  await page.getByText('Backup backup-new created.').waitFor({ state: 'visible' });
  assert.equal(backupCreated, true);

  await page.getByRole('button', { name: 'Apply protection' }).click();
  await page.getByText('Protection applied. 0 issue(s) remain.').waitFor({ state: 'visible' });
  assert.equal(protectionApplied, true);

  await page.getByRole('button', { name: 'Create checkpoint' }).click();
  await page.getByText('Checkpoint created.').waitFor({ state: 'visible' });
  assert.equal(checkpointCreated, true);

  await page.getByRole('button', { name: 'Preview restore' }).click();
  await page.getByText('Read-only restore preview loaded. No files were changed.').waitFor({ state: 'visible' });
  await page.getByText('plans/plan.md').waitFor({ state: 'visible' });
  assert.equal(restorePreviewRequested, true);
});
