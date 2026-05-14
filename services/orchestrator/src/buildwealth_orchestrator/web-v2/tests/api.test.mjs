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
  await api.accountDataDeletionPreview('household');
  await api.accountDataDeletionRequests();
  await api.requestAccountDataDeletion({ scope: 'workspace', confirm: 'delete workspace data' });
  await api.cancelAccountDataDeletion('del_123');
  await api.changeAccountPassword({ current_password: 'old-password', new_password: 'new-password' });
  await api.deactivateAccount({ current_password: 'new-password', confirm: 'deactivate' });
  setCsrfToken('csrf-token-456');
  setActiveWorkspaceId('ws_demo_household');
  await api.closeHostedAccount({ confirm: 'close buildwealth access' });
  await api.today();

  assert.equal(requests[0].url, '/api/account/export');
  assert.equal(requests[0].options.method || 'GET', 'GET');
  assert.equal(requests[0].options.headers['x-buildwealth-workspace-id'], 'ws_demo_household');

  assert.equal(requests[1].url, '/api/account/data-deletion/preview?scope=household');
  assert.equal(requests[1].options.method || 'GET', 'GET');
  assert.equal(requests[2].url, '/api/account/data-deletion/requests');
  assert.equal(requests[2].options.method || 'GET', 'GET');

  assert.equal(requests[3].url, '/api/account/data-deletion/request');
  assert.equal(requests[3].options.method, 'POST');
  assert.equal(requests[3].options.headers['x-buildwealth-csrf-token'], 'csrf-token-123');

  assert.equal(requests[4].url, '/api/account/data-deletion/del_123/cancel');
  assert.equal(requests[4].options.method, 'POST');
  assert.equal(requests[4].options.headers['x-buildwealth-csrf-token'], 'csrf-token-123');

  assert.equal(requests[5].url, '/api/account/password');
  assert.equal(requests[5].options.method, 'POST');
  assert.equal(requests[5].options.headers['x-buildwealth-csrf-token'], 'csrf-token-123');

  assert.equal(requests[6].url, '/api/account');
  assert.equal(requests[6].options.method, 'DELETE');
  assert.equal(requests[6].options.headers['x-buildwealth-csrf-token'], 'csrf-token-123');

  assert.equal(requests[7].url, '/api/account/hosted/close');
  assert.equal(requests[7].options.method, 'POST');
  assert.equal(requests[7].options.headers['x-buildwealth-csrf-token'], 'csrf-token-456');

  assert.equal(requests[8].url, '/api/dashboard/today');
  assert.equal(requests[8].options.headers['x-buildwealth-workspace-id'], undefined);
});

test('security helpers call secret key rotation preview and apply routes', async () => {
  const requests = [];
  globalThis.fetch = async (url, options = {}) => {
    requests.push({ url, options });
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  };

  setCsrfToken('csrf-token-rotation');
  await api.previewSecretKeyRotation();
  await api.applySecretKeyRotation({ confirm: 'rotate' });

  assert.equal(requests[0].url, '/api/security/secrets/rotation/preview');
  assert.equal(requests[0].options.method || 'GET', 'GET');
  assert.equal(requests[1].url, '/api/security/secrets/rotation/apply');
  assert.equal(requests[1].options.method, 'POST');
  assert.equal(requests[1].options.headers['x-buildwealth-csrf-token'], 'csrf-token-rotation');
});
