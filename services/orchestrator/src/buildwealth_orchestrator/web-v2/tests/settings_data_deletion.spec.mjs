import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, extname, isAbsolute, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, test } from '@playwright/test';

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

test('Settings previews schedules and cancels BuildWealth data deletion', async ({ page }) => {
  let deletionRequested = false;
  let deletionCanceled = false;

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

    if (url.pathname === '/api/settings') {
      await route.fulfill(jsonResponse({
        llm_provider: 'openai',
        llm_api_key: '',
        llm_model: 'gpt-5.5',
        llm_base_url: 'https://api.openai.com/v1',
        llm_max_tokens: 2048,
        llm_timeout_seconds: 60,
        llm_parallel_tool_calls: true,
      }));
      return;
    }

    if (url.pathname === '/api/settings/context') {
      await route.fulfill(jsonResponse({
        context_embeddings_enabled: false,
        context_embedding_provider: 'disabled',
        context_embedding_model: 'nomic-embed-text',
        context_embedding_base_url: 'http://localhost:11434',
        context_embedding_timeout_seconds: 5,
      }));
      return;
    }

    if (url.pathname === '/api/workspaces') {
      await route.fulfill(jsonResponse({
        active_workspace_id: 'ws_household',
        items: [
          { id: 'ws_household', name: 'My Household', workspace_type: 'household', is_demo: false },
          { id: 'ws_demo', name: 'Demo Household', workspace_type: 'demo', is_demo: true },
        ],
      }));
      return;
    }

    if (url.pathname === '/api/auth/session') {
      await route.fulfill(jsonResponse({
        authenticated: true,
        csrf_token: 'csrf-token-123',
        user: {
          id: 'usr_owner',
          email: 'owner@example.test',
          display_name: 'Owner',
          auth_provider: 'local',
        },
        workspace: { id: 'ws_household', name: 'My Household', workspace_type: 'household', is_demo: false },
        permissions: ['account.delete', 'account.export'],
      }));
      return;
    }

    if (url.pathname === '/api/auth/config') {
      await route.fulfill(jsonResponse({
        local_auth_enabled: true,
        hosted_auth_enabled: false,
      }));
      return;
    }

    if (url.pathname === '/api/account/data-deletion/requests') {
      await route.fulfill(jsonResponse({
        items: deletionRequested && !deletionCanceled ? [
          {
            id: 'del_123',
            status: 'pending',
            scope: 'workspace',
            purge_after: '2026-06-13T12:00:00Z',
            preview: { affected_workspace_count: 1 },
          },
        ] : [],
      }));
      return;
    }

    if (url.pathname === '/api/account/data-deletion/preview') {
      await route.fulfill(jsonResponse({
        schema_version: 1,
        scope: url.searchParams.get('scope') || 'workspace',
        can_request: true,
        affected_workspace_count: 1,
        recovery_window_days: 30,
        purge_after: '2026-06-13T12:00:00Z',
        confirmation_phrase: 'delete workspace data',
        totals: {
          workspace_count: 1,
          file_count: 42,
          size_bytes: 1536,
          secret_count: 2,
          backup_archive_count: 3,
        },
        will_retain: ['minimal audit events', 'hosted identity provider account unless deleted by the provider'],
      }));
      return;
    }

    if (url.pathname === '/api/account/data-deletion/request') {
      deletionRequested = true;
      await route.fulfill(jsonResponse({
        ok: true,
        message: 'Data deletion scheduled. You can cancel during the recovery window.',
        request: {
          id: 'del_123',
          status: 'pending',
          scope: 'workspace',
          purge_after: '2026-06-13T12:00:00Z',
          preview: { affected_workspace_count: 1 },
        },
      }));
      return;
    }

    if (url.pathname === '/api/account/data-deletion/del_123/cancel') {
      deletionCanceled = true;
      await route.fulfill(jsonResponse({
        ok: true,
        message: 'Data deletion canceled.',
        request: {
          id: 'del_123',
          status: 'canceled',
          scope: 'workspace',
          purge_after: '2026-06-13T12:00:00Z',
          preview: { affected_workspace_count: 1 },
        },
      }));
      return;
    }

    await route.fulfill(jsonResponse({ ok: true }));
  });

  await page.goto('http://buildwealth-v2.test/#settings');

  await expect(page.getByText('Delete BuildWealth data')).toBeVisible();
  await page.getByRole('button', { name: 'Preview deletion' }).click();
  await expect(page.getByText('42 files')).toBeVisible();
  await expect(page.getByText('2 secret keys')).toBeVisible();
  await expect(page.getByText('3 backup archives')).toBeVisible();

  await page.getByLabel('Type delete workspace data').fill('delete workspace data');
  await page.getByRole('button', { name: 'Schedule deletion' }).click();
  await expect(page.getByText('Data deletion scheduled. You can cancel during the recovery window.')).toBeVisible();
  await expect(page.getByText('Workspace deletion pending')).toBeVisible();

  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByText('Data deletion canceled.')).toBeVisible();
});
