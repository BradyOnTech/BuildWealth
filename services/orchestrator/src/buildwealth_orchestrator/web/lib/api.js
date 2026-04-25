export async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.text();
  if (!body.trim()) {
    if (!response.ok) {
      throw new Error(response.statusText || `Request failed with ${response.status}`);
    }
    throw new Error(`Expected JSON response from ${url}, received an empty body.`);
  }

  let data;
  try {
    data = JSON.parse(body);
  } catch {
    if (response.ok) {
      throw new Error(`Expected JSON response from ${url}, received invalid JSON.`);
    }
    throw new Error(`Request to ${url} failed with ${response.status} ${response.statusText || 'Unknown status'}, and the error body was not valid JSON.`);
  }

  if (!response.ok) {
    const detail = data && typeof data === 'object' ? data.detail || data.message : null;
    if (detail) {
      throw new Error(detail);
    }
    throw new Error(response.statusText || `Request failed with ${response.status}`);
  }
  return data;
}

export function getGitPolicy() {
  return fetchJson('/api/git/policy');
}

export function updateGitPolicy(payload) {
  return fetchJson('/api/git/policy', {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function initializeGitRepository() {
  return fetchJson('/api/git/init', { method: 'POST' });
}

export function getGitStatus() {
  return fetchJson('/api/git/status');
}

export function getGitHistory(limit = 10) {
  return fetchJson(`/api/git/history?limit=${encodeURIComponent(limit)}`);
}

export function getGitActivity({ limit = 20, eventType = '', status = '', ref = '' } = {}) {
  const params = new URLSearchParams();
  if (limit) params.set('limit', String(limit));
  if (eventType) params.set('event_type', eventType);
  if (status) params.set('status', status);
  if (ref) params.set('ref', ref);
  const query = params.toString();
  return fetchJson(`/api/git/activity${query ? `?${query}` : ''}`);
}

export function getGitDiff({ ref = '', path = '', maxChars = 200000 } = {}) {
  const params = new URLSearchParams();
  if (ref) params.set('ref', ref);
  if (path) params.set('path', path);
  if (maxChars) params.set('max_chars', String(maxChars));
  const query = params.toString();
  return fetchJson(`/api/git/diff${query ? `?${query}` : ''}`);
}

export function getGitRestorePreview({ ref = '', path = '', maxChars = 120000 } = {}) {
  const params = new URLSearchParams();
  if (ref) params.set('ref', ref);
  if (path) params.set('path', path);
  if (maxChars) params.set('max_chars', String(maxChars));
  const query = params.toString();
  return fetchJson(`/api/git/restore-preview${query ? `?${query}` : ''}`);
}

export function applyGitRestore(payload = {}) {
  return fetchJson('/api/git/restore-apply', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function getGitAutoGitState() {
  return fetchJson('/api/git/autogit');
}

export function runDueGitAutoGit() {
  return fetchJson('/api/git/autogit/run-due', { method: 'POST' });
}

export function connectGitRemote(payload = {}) {
  return fetchJson('/api/git/remote/connect', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function pushGitRemote(payload = {}) {
  return fetchJson('/api/git/push', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function pullGitRemote(payload = {}) {
  return fetchJson('/api/git/pull', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function createGitCheckpoint(payload = {}) {
  return fetchJson('/api/git/checkpoint', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
