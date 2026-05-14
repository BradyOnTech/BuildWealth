import test from 'node:test';
import assert from 'node:assert/strict';

const storage = new Map();

globalThis.window = {
  sessionStorage: {
    getItem: key => storage.get(key) || '',
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: key => storage.delete(key),
  },
};

const { api, setActiveWorkspaceId } = await import('../lib/api.js');

test('api client sends the active workspace header on later requests', async () => {
  const requests = [];
  globalThis.fetch = async (url, options = {}) => {
    requests.push({ url, options });
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  };

  setActiveWorkspaceId('ws_demo_household');
  await api.today();

  assert.equal(requests[0].url, '/api/dashboard/today');
  assert.equal(requests[0].options.headers['x-buildwealth-workspace-id'], 'ws_demo_household');
});

test('workspace selection persists only after the server accepts the switch', async () => {
  const requests = [];
  globalThis.fetch = async (url, options = {}) => {
    requests.push({ url, options });
    return new Response(JSON.stringify({ id: 'ws_demo_household' }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  };

  setActiveWorkspaceId('');
  await api.selectWorkspace('ws_demo_household');
  await api.holdings();

  assert.equal(requests[0].url, '/api/workspaces/ws_demo_household/select');
  assert.equal(requests[1].url, '/api/portfolio/holdings');
  assert.equal(requests[1].options.headers['x-buildwealth-workspace-id'], 'ws_demo_household');
});
