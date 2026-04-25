import test from 'node:test';
import assert from 'node:assert/strict';

import {
  applyGitRestore,
  createGitCheckpoint,
  connectGitRemote,
  getGitAutoGitState,
  getGitDiff,
  getGitHistory,
  getGitPolicy,
  getGitRestorePreview,
  getGitStatus,
  initializeGitRepository,
  runDueGitAutoGit,
  pushGitRemote,
  pullGitRemote,
  updateGitPolicy,
} from '../lib/api.js';

function installFetchMock(assertRequest) {
  globalThis.fetch = async (url, options = {}) => {
    assertRequest(String(url), options);
    return {
      ok: true,
      text: async () => JSON.stringify({ ok: true }),
    };
  };
}

test('git API helpers target the expected endpoints', async () => {
  const calls = [];
  installFetchMock((url, options) => {
    calls.push({ url, method: options.method || 'GET' });
  });

  await getGitPolicy();
  await updateGitPolicy({ enabled: true });
  await initializeGitRepository();
  await getGitStatus();
  await getGitHistory(7);
  await getGitDiff({ ref: 'abc123', maxChars: 1234 });
  await getGitRestorePreview({ ref: 'abc123', path: 'plans/plan-a/plan.md', maxChars: 4321 });
  await applyGitRestore({ ref: 'abc123', paths: ['plans/plan-a/plan.md'], confirmation: 'APPLY_GIT_RESTORE' });
  await getGitAutoGitState();
  await runDueGitAutoGit();
  await connectGitRemote({ remote_url: 'git@example.com:repo.git', remote_name: 'origin' });
  await pushGitRemote({ remote_name: 'origin' });
  await pullGitRemote({ remote_name: 'origin' });
  await createGitCheckpoint({ event_type: 'manual_checkpoint' });

  assert.deepEqual(calls, [
    { url: '/api/git/policy', method: 'GET' },
    { url: '/api/git/policy', method: 'PUT' },
    { url: '/api/git/init', method: 'POST' },
    { url: '/api/git/status', method: 'GET' },
    { url: '/api/git/history?limit=7', method: 'GET' },
    { url: '/api/git/diff?ref=abc123&max_chars=1234', method: 'GET' },
    { url: '/api/git/restore-preview?ref=abc123&path=plans%2Fplan-a%2Fplan.md&max_chars=4321', method: 'GET' },
    { url: '/api/git/restore-apply', method: 'POST' },
    { url: '/api/git/autogit', method: 'GET' },
    { url: '/api/git/autogit/run-due', method: 'POST' },
    { url: '/api/git/remote/connect', method: 'POST' },
    { url: '/api/git/push', method: 'POST' },
    { url: '/api/git/pull', method: 'POST' },
    { url: '/api/git/checkpoint', method: 'POST' },
  ]);
});

test('git policy, checkpoint, and restore-apply helpers send JSON bodies', async () => {
  installFetchMock((url, options) => {
    if (url === '/api/git/policy') {
      assert.equal(options.headers['content-type'], 'application/json');
      assert.deepEqual(JSON.parse(options.body), { enabled: true });
    }
    if (url === '/api/git/checkpoint') {
      assert.equal(options.headers['content-type'], 'application/json');
      assert.deepEqual(JSON.parse(options.body), { event_type: 'manual_checkpoint' });
    }
    if (url === '/api/git/restore-apply') {
      assert.equal(options.headers['content-type'], 'application/json');
      assert.deepEqual(JSON.parse(options.body), {
        ref: 'abc123',
        paths: ['plans/plan-a/plan.md'],
        confirmation: 'APPLY_GIT_RESTORE',
      });
    }
  });

  await updateGitPolicy({ enabled: true });
  await createGitCheckpoint({ event_type: 'manual_checkpoint' });
  await applyGitRestore({
    ref: 'abc123',
    paths: ['plans/plan-a/plan.md'],
    confirmation: 'APPLY_GIT_RESTORE',
  });
});
