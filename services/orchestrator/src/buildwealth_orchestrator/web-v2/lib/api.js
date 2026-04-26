// Minimal JSON fetch helper for v2.
// Forked from web/lib/api.js — kept tiny on purpose; v2 grows its own surface.

export async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.text();

  if (!body.trim()) {
    if (!response.ok) {
      throw new Error(response.statusText || `Request failed with ${response.status}`);
    }
    throw new Error(`Expected JSON from ${url}, received empty body.`);
  }

  let data;
  try {
    data = JSON.parse(body);
  } catch {
    if (response.ok) {
      throw new Error(`Expected JSON from ${url}, received invalid JSON.`);
    }
    throw new Error(`Request to ${url} failed with ${response.status} ${response.statusText || ''}`.trim());
  }

  if (!response.ok) {
    const detail = data && typeof data === 'object' ? data.detail || data.message : null;
    throw new Error(detail || response.statusText || `Request failed with ${response.status}`);
  }

  return data;
}

function postJson(url, body = {}) {
  return fetchJson(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

function putJson(url, body = {}) {
  return fetchJson(url, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

function recommendationsUrl({ status = '', planId = '', sort = 'ranked', limit = 200 } = {}) {
  const params = new URLSearchParams();
  params.set('limit', String(limit));
  if (sort) params.set('sort', sort);
  if (status && status !== 'all') params.set('status', status);
  if (planId && planId !== 'all') params.set('plan_id', planId);
  return `/api/recommendations?${params.toString()}`;
}

export const api = {
  today:        () => fetchJson('/api/dashboard/today'),
  refreshTodayResearch: () => postJson('/api/dashboard/today/research-readiness/refresh', {}),
  engines:      () => fetchJson('/api/engines/status'),
  telemetry:    () => fetchJson('/api/telemetry/runtime'),
  syncStatus:   () => fetchJson('/api/sync/status'),
  plans:        (limit = 200) => fetchJson(`/api/plans?limit=${limit}`),
  plan:         (id) => fetchJson(`/api/plans/${encodeURIComponent(id)}`),
  planTracking: (id) => fetchJson(`/api/plans/${encodeURIComponent(id)}/tracking`),
  createPlan:   (body) => postJson('/api/plans', body),
  appendDecision: (id, body) => postJson(`/api/plans/${encodeURIComponent(id)}/decisions`, body),
  setActivePlan: (id) => postJson(`/api/plans/${encodeURIComponent(id)}/activate`, {}),
  holdings:     () => fetchJson('/api/portfolio/holdings'),
  portfolioFit: (body) => postJson('/api/portfolio/fit-assessment', body),
  profile:      () => fetchJson('/api/financial-profile'),
  updateProfile: (body) => putJson('/api/financial-profile', body),
  onboarding:   () => fetchJson('/api/onboarding/status'),

  // Copilot
  conversations:     (limit = 25) => fetchJson(`/api/copilot/conversations?limit=${limit}`),
  conversation:      (id) => fetchJson(`/api/copilot/conversations/${encodeURIComponent(id)}`),
  copilotChat:       (body) => postJson('/api/copilot/chat', body),

  // Recommendations
  recommendations: (opts) => fetchJson(recommendationsUrl(opts)),
  recommendation:  (id)   => fetchJson(`/api/recommendations/${encodeURIComponent(id)}`),
  preview:         (id, body = {}) => postJson(`/api/recommendations/${encodeURIComponent(id)}/preview`, body),
  apply:           (id, body = {}) => postJson(`/api/recommendations/${encodeURIComponent(id)}/apply`, body),
  reject:          (id, body = {}) => postJson(`/api/recommendations/${encodeURIComponent(id)}/reject`, body),
  archive:         (id, body = {}) => postJson(`/api/recommendations/${encodeURIComponent(id)}/archive`, body),
  outcome:         (id, body = {}) => postJson(`/api/recommendations/${encodeURIComponent(id)}/outcome`, body),
  closure:         (planId)        => fetchJson(planId ? `/api/recommendations/closure-analytics?plan_id=${encodeURIComponent(planId)}` : '/api/recommendations/closure-analytics'),
  sweepPreview:    (body = {})     => postJson('/api/recommendations/generate/run-all', { ...body, dry_run: true }),
  sweepCreate:     (body = {})     => postJson('/api/recommendations/generate/run-all', { ...body, dry_run: false }),
};
