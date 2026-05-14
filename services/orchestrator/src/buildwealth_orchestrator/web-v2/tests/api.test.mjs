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

const { api, setActiveWorkspaceId, setCsrfToken } = await import('../lib/api.js');

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

test('account helpers use protected routes and clear session state after deactivation', async () => {
  const requests = [];
  globalThis.fetch = async (url, options = {}) => {
    requests.push({ url, options });
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  };

  setCsrfToken('csrf-token-123');
  setActiveWorkspaceId('ws_demo_household');

  await api.exportAccount();
  await api.changeAccountPassword({ current_password: 'old-password', new_password: 'new-password' });
  await api.deactivateAccount({ current_password: 'new-password', confirm: 'deactivate' });
  await api.today();

  assert.equal(requests[0].url, '/api/account/export');
  assert.equal(requests[0].options.method || 'GET', 'GET');
  assert.equal(requests[0].options.headers['x-buildwealth-workspace-id'], 'ws_demo_household');

  assert.equal(requests[1].url, '/api/account/password');
  assert.equal(requests[1].options.method, 'POST');
  assert.equal(requests[1].options.headers['x-buildwealth-csrf-token'], 'csrf-token-123');

  assert.equal(requests[2].url, '/api/account');
  assert.equal(requests[2].options.method, 'DELETE');
  assert.equal(requests[2].options.headers['x-buildwealth-csrf-token'], 'csrf-token-123');

  assert.equal(requests[3].url, '/api/dashboard/today');
  assert.equal(requests[3].options.headers['x-buildwealth-workspace-id'], undefined);
});
