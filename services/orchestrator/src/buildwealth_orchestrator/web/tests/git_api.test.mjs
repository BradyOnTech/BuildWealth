import test from 'node:test';
import assert from 'node:assert/strict';

import {
  createGitCheckpoint,
  getGitAutoGitState,
  getGitDiff,
  getGitHistory,
  getGitPolicy,
  getGitStatus,
  initializeGitRepository,
  runDueGitAutoGit,
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
  await getGitAutoGitState();
  await runDueGitAutoGit();
  await createGitCheckpoint({ event_type: 'manual_checkpoint' });

  assert.deepEqual(calls, [
    { url: '/api/git/policy', method: 'GET' },
    { url: '/api/git/policy', method: 'PUT' },
    { url: '/api/git/init', method: 'POST' },
    { url: '/api/git/status', method: 'GET' },
    { url: '/api/git/history?limit=7', method: 'GET' },
    { url: '/api/git/diff?ref=abc123&max_chars=1234', method: 'GET' },
    { url: '/api/git/autogit', method: 'GET' },
    { url: '/api/git/autogit/run-due', method: 'POST' },
    { url: '/api/git/checkpoint', method: 'POST' },
  ]);
});

test('git policy update and checkpoint helpers send JSON bodies', async () => {
  installFetchMock((url, options) => {
    if (url === '/api/git/policy') {
      assert.equal(options.headers['content-type'], 'application/json');
      assert.deepEqual(JSON.parse(options.body), { enabled: true });
    }
    if (url === '/api/git/checkpoint') {
      assert.equal(options.headers['content-type'], 'application/json');
      assert.deepEqual(JSON.parse(options.body), { event_type: 'manual_checkpoint' });
    }
  });

  await updateGitPolicy({ enabled: true });
  await createGitCheckpoint({ event_type: 'manual_checkpoint' });
});
