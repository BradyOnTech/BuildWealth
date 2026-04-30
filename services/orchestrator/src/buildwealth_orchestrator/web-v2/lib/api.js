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

function patchJson(url, body = {}) {
  return fetchJson(url, {
    method: 'PATCH',
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

function researchDossiersUrl({ planId = '', limit = 10, includeContent = false } = {}) {
  const params = new URLSearchParams();
  params.set('limit', String(limit));
  if (planId) params.set('plan_id', planId);
  if (includeContent) params.set('include_content', 'true');
  return `/api/research/dossiers?${params.toString()}`;
}

function gitRestorePreviewUrl({ ref = '', path = '', maxChars = 120000 } = {}) {
  const params = new URLSearchParams();
  params.set('ref', ref);
  params.set('max_chars', String(maxChars));
  if (path) params.set('path', path);
  return `/api/git/restore-preview?${params.toString()}`;
}

function financialProfileUrl({ source = '' } = {}) {
  const params = new URLSearchParams();
  if (source) params.set('source', source);
  const query = params.toString();
  return query ? `/api/financial-profile?${query}` : '/api/financial-profile';
}

export const api = {
  today:        () => fetchJson('/api/dashboard/today'),
  recordTodayReview: () => postJson('/api/dashboard/today/review-checkpoint', {}),
  refreshTodayResearch: () => postJson('/api/dashboard/today/research-readiness/refresh', {}),
  engines:      () => fetchJson('/api/engines/status'),
  telemetry:    () => fetchJson('/api/telemetry/runtime'),
  syncStatus:   () => fetchJson('/api/sync/status'),
  durableStorageStatus: () => fetchJson('/api/storage/durable/status'),
  storageBackups: () => fetchJson('/api/storage/backups'),
  createStorageBackup: (body = {}) => postJson('/api/storage/backups', body),
  storageProtectionStatus: () => fetchJson('/api/storage/protection/status'),
  applyStorageProtection: (body = {}) => postJson('/api/storage/protection/apply', body),
  gitStatus: () => fetchJson('/api/git/status'),
  gitHistory: (limit = 20) => fetchJson(`/api/git/history?limit=${encodeURIComponent(limit)}`),
  createGitCheckpoint: (body = {}) => postJson('/api/git/checkpoint', body),
  gitRestorePreview: (opts = {}) => fetchJson(gitRestorePreviewUrl(opts)),
  gitActivity: (opts = {}) => fetchJson(`/api/git/activity?${new URLSearchParams({
    limit: String(opts.limit || 25),
  }).toString()}`),
  plans:        (limit = 200) => fetchJson(`/api/plans?limit=${limit}`),
  plan:         (id) => fetchJson(`/api/plans/${encodeURIComponent(id)}`),
  planTracking: (id) => fetchJson(`/api/plans/${encodeURIComponent(id)}/tracking`),
  planSettings: (id, body = {}) => patchJson(`/api/plans/${encodeURIComponent(id)}/settings`, body),
  planTimeline: (id) => fetchJson(`/api/plans/${encodeURIComponent(id)}/timeline`),
  updatePlanTimeline: (id, body = {}) => putJson(`/api/plans/${encodeURIComponent(id)}/timeline`, body),
  planContributionRules: (id) => fetchJson(`/api/plans/${encodeURIComponent(id)}/contribution-rules`),
  updatePlanContributionRules: (id, body = {}) => putJson(`/api/plans/${encodeURIComponent(id)}/contribution-rules`, body),
  planAssumptionSets: (id) => fetchJson(`/api/plans/${encodeURIComponent(id)}/assumption-sets`),
  updatePlanAssumptionSets: (id, body = {}) => putJson(`/api/plans/${encodeURIComponent(id)}/assumption-sets`, body),
  planScenarioDiff: (id, body = {}) => postJson(`/api/plans/${encodeURIComponent(id)}/scenario-diff`, body),
  planBranchTemplates: (id) => fetchJson(`/api/plans/${encodeURIComponent(id)}/branch-templates`),
  updatePlanBranchTemplates: (id, body = {}) => putJson(`/api/plans/${encodeURIComponent(id)}/branch-templates`, body),
  planScenarioBranch: (id, body = {}) => postJson(`/api/plans/${encodeURIComponent(id)}/scenario-branch`, body),
  planWithdrawalStrategyCompare: (id, body = {}) => postJson(`/api/plans/${encodeURIComponent(id)}/withdrawal-strategy-compare`, body),
  refreshPlanContext: (id) => postJson(`/api/plans/${encodeURIComponent(id)}/refresh-context`, {}),
  createPlan:   (body) => postJson('/api/plans', body),
  appendDecision: (id, body) => postJson(`/api/plans/${encodeURIComponent(id)}/decisions`, body),
  setActivePlan: (id) => postJson(`/api/plans/${encodeURIComponent(id)}/activate`, {}),
  holdings:     () => fetchJson('/api/portfolio/holdings'),
  watchlist:    (opts = {}) => fetchJson(`/api/portfolio/watchlist?${new URLSearchParams({
    limit: String(opts.limit || 200),
    sort: opts.sort || 'symbol',
    period: opts.period || '6mo',
    interval: opts.interval || '1d',
  }).toString()}`),
  saveWatchlistThesisRevision: (symbol, body = {}) => putJson(
    `/api/portfolio/watchlist/${encodeURIComponent(symbol)}/thesis`,
    body,
  ),
  saveDossierThesisRevision: (planId, artifactId, body = {}) => putJson(
    `/api/plans/${encodeURIComponent(planId)}/artifacts/${encodeURIComponent(artifactId)}/thesis`,
    body,
  ),
  portfolioFit: (body) => postJson('/api/portfolio/fit-assessment', body),
  researchEvidencePacket: (body) => postJson('/api/research/evidence-packet', body),
  researchCompare: (body) => postJson('/api/research/compare', body),
  researchDossiers: (opts = {}) => fetchJson(researchDossiersUrl(opts)),
  planArtifact: (planId, artifactId) => fetchJson(`/api/plans/${encodeURIComponent(planId)}/artifacts/${encodeURIComponent(artifactId)}`),
  profile:      () => fetchJson('/api/financial-profile'),
  updateProfile: (body, opts = {}) => putJson(financialProfileUrl(opts), body),
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
