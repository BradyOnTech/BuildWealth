// Minimal JSON fetch helper for v2.
// Forked from web/lib/api.js — kept tiny on purpose; v2 grows its own surface.

const CSRF_STORAGE_KEY = 'buildwealth.csrf_token';
const WORKSPACE_STORAGE_KEY = 'buildwealth.active_workspace_id';

let csrfToken = readStoredCsrfToken();
let activeWorkspaceId = readStoredWorkspaceId();

function readStoredCsrfToken() {
  try { return window.sessionStorage.getItem(CSRF_STORAGE_KEY) || ''; }
  catch { return ''; }
}

export function setCsrfToken(token) {
  csrfToken = String(token || '');
  try {
    if (csrfToken) window.sessionStorage.setItem(CSRF_STORAGE_KEY, csrfToken);
    else window.sessionStorage.removeItem(CSRF_STORAGE_KEY);
  } catch {
    // Storage can be unavailable in private contexts; cookie auth still works.
  }
}

function readStoredWorkspaceId() {
  try { return window.sessionStorage.getItem(WORKSPACE_STORAGE_KEY) || ''; }
  catch { return ''; }
}

export function setActiveWorkspaceId(workspaceId) {
  activeWorkspaceId = String(workspaceId || '');
  try {
    if (activeWorkspaceId) window.sessionStorage.setItem(WORKSPACE_STORAGE_KEY, activeWorkspaceId);
    else window.sessionStorage.removeItem(WORKSPACE_STORAGE_KEY);
  } catch {
    // Workspace selection still works for signed-in sessions via the server cookie.
  }
}

function withAuthHeaders(options = {}) {
  const method = String(options.method || 'GET').toUpperCase();
  const headers = { ...(options.headers || {}) };
  if (csrfToken && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    headers['x-buildwealth-csrf-token'] = csrfToken;
  }
  if (activeWorkspaceId && !headers['x-buildwealth-workspace-id']) {
    headers['x-buildwealth-workspace-id'] = activeWorkspaceId;
  }
  return {
    credentials: 'same-origin',
    ...options,
    headers,
  };
}

export async function fetchJson(url, options = {}) {
  const response = await fetch(url, withAuthHeaders(options));
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
    const message = typeof detail === 'string'
      ? detail
      : (detail ? safeJson(detail) : (response.statusText || `Request failed with ${response.status}`));
    const error = new Error(message);
    error.status = response.status;
    error.detail = detail;       // structured shape if the server sent one
    error.body = data;           // raw parsed body, if callers need more
    throw error;
  }

  return data;
}

function safeJson(value) {
  try { return JSON.stringify(value); }
  catch { return String(value); }
}

function postJson(url, body = {}) {
  return fetchJson(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

function postForm(url, formData) {
  return fetchJson(url, {
    method: 'POST',
    body: formData,
  });
}

/* Parse a server-sent-events byte stream, invoking onEvent(parsedJson) for
   each `data:` line. Exported for unit tests. */
export function parseSseChunk(buffer, chunk, onEvent) {
  let text = buffer + chunk;
  const events = [];
  let idx;
  while ((idx = text.indexOf('\n')) >= 0) {
    const line = text.slice(0, idx).replace(/\r$/, '');
    text = text.slice(idx + 1);
    if (!line.startsWith('data:')) continue;
    const payload = line.slice(5).trim();
    if (!payload) continue;
    try { events.push(JSON.parse(payload)); }
    catch { /* ignore malformed event lines */ }
  }
  for (const event of events) onEvent(event);
  return text;
}

/* POST to an SSE endpoint and dispatch each event to onEvent. Resolves when
   the stream ends; rejects on network failure, non-2xx, or non-SSE replies
   (callers fall back to the blocking endpoint). Abort via options.signal. */
export async function fetchSse(url, body, { signal, onEvent } = {}) {
  const response = await fetch(url, withAuthHeaders({
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  }));
  const contentType = response.headers.get('content-type') || '';
  if (!response.ok || !contentType.includes('text/event-stream') || !response.body) {
    const error = new Error(`Streaming unavailable (${response.status})`);
    error.status = response.status;
    error.streamingUnavailable = true;
    throw error;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer = parseSseChunk(buffer, decoder.decode(value, { stream: true }), onEvent);
  }
  parseSseChunk(buffer, '\n', onEvent);
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

function deleteJson(url, body = {}) {
  return fetchJson(url, {
    method: 'DELETE',
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

function portfolioAssetSearchUrl({ q = '', limit = 100 } = {}) {
  const params = new URLSearchParams();
  params.set('limit', String(limit));
  if (q) params.set('q', q);
  return `/api/portfolio/assets/search?${params.toString()}`;
}

function contextCandidatesUrl({
  lifecycleState = '',
  includeArchived = false,
  limit = 100,
} = {}) {
  const params = new URLSearchParams();
  params.set('limit', String(limit));
  if (lifecycleState && lifecycleState !== 'all') params.set('lifecycle_state', lifecycleState);
  if (includeArchived) params.set('include_archived', 'true');
  return `/api/context/candidates?${params.toString()}`;
}

export const api = {
  authConfig: () => fetchJson('/api/auth/config'),
  hostedAuthReadiness: () => fetchJson('/api/auth/hosted/readiness'),
  codexSubscriptionStatus: () => fetchJson('/api/settings/codex-subscription'),
  connectCodexSubscription: () => postJson('/api/settings/codex-subscription/connect', {}),
  disconnectCodexSubscription: () => postJson('/api/settings/codex-subscription/disconnect', {}),
  authLogin: async (body = {}) => {
    const result = await postJson('/api/auth/login', body);
    setCsrfToken(result?.csrf_token || '');
    setActiveWorkspaceId(result?.workspace_id || '');
    return result;
  },
  authRegister: async (body = {}) => {
    const result = await postJson('/api/auth/register', body);
    setCsrfToken(result?.csrf_token || '');
    setActiveWorkspaceId(result?.workspace_id || '');
    return result;
  },
  authLogout: async () => {
    try { return await postJson('/api/auth/logout', {}); }
    finally {
      setCsrfToken('');
      setActiveWorkspaceId('');
    }
  },
  authSession: async () => {
    const result = await fetchJson('/api/auth/session');
    if (result?.csrf_token) setCsrfToken(result.csrf_token);
    if (!activeWorkspaceId && result?.workspace?.id) setActiveWorkspaceId(result.workspace.id);
    return result;
  },
  changeAccountPassword: (body = {}) => postJson('/api/account/password', body),
  exportAccount: () => fetchJson('/api/account/export'),
  accountDataDeletionPreview: (scope = 'workspace') => {
    const params = new URLSearchParams({ scope: String(scope || 'workspace') });
    return fetchJson(`/api/account/data-deletion/preview?${params.toString()}`);
  },
  accountDataDeletionRequests: () => fetchJson('/api/account/data-deletion/requests'),
  requestAccountDataDeletion: (body = {}) => postJson('/api/account/data-deletion/request', body),
  cancelAccountDataDeletion: (requestId) => {
    return postJson(`/api/account/data-deletion/${encodeURIComponent(requestId)}/cancel`, {});
  },
  deactivateAccount: async (body = {}) => {
    try { return await deleteJson('/api/account', body); }
    finally {
      setCsrfToken('');
      setActiveWorkspaceId('');
    }
  },
  closeHostedAccount: async (body = {}) => {
    try { return await postJson('/api/account/hosted/close', body); }
    finally {
      setCsrfToken('');
      setActiveWorkspaceId('');
    }
  },
  previewSecretKeyRotation: () => fetchJson('/api/security/secrets/rotation/preview'),
  applySecretKeyRotation: (body = {}) => postJson('/api/security/secrets/rotation/apply', body),
  workspaces: () => fetchJson('/api/workspaces'),
  currentWorkspace: () => fetchJson('/api/workspaces/current'),
  selectWorkspace: async (workspaceId) => {
    const result = await postJson(`/api/workspaces/${encodeURIComponent(workspaceId)}/select`, {});
    setActiveWorkspaceId(workspaceId);
    return result;
  },
  resetDemoWorkspace: (workspaceId) => postJson(`/api/workspaces/${encodeURIComponent(workspaceId)}/demo/reset`, {}),

  today:        () => fetchJson('/api/dashboard/today'),
  morningBrief:       () => fetchJson('/api/dashboard/brief'),
  taxLossHarvest:     () => fetchJson('/api/tax/loss-harvest'),
  rothLadder:         (body = {}) => postJson('/api/tax/roth-ladder', body),
  markBriefSeen:      () => postJson('/api/dashboard/brief/seen', {}),
  financialHealth: () => fetchJson('/api/financial-health'),
  affordability: (body = {}) => postJson('/api/affordability', body),
  recordTodayReview: () => postJson('/api/dashboard/today/review-checkpoint', {}),
  refreshTodayResearch: () => postJson('/api/dashboard/today/research-readiness/refresh', {}),
  services:     () => fetchJson('/api/services/status'),
  telemetry:    () => fetchJson('/api/telemetry/runtime'),
  syncStatus:   () => fetchJson('/api/sync/status'),
  durableStorageStatus: () => fetchJson('/api/storage/durable/status'),
  releaseReadiness: () => fetchJson('/api/release-readiness'),
  recordReleaseWorkflowVerification: (body = {}) => postJson('/api/release-readiness/workflow-verification', body),
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
  planningAssumptionDefaults: () => fetchJson('/api/planning/assumption-defaults'),
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
  explainPlanSimulation: (id, body = {}) => postJson(`/api/plans/${encodeURIComponent(id)}/simulation-explain`, body),
  planWhatIfReviewLevel: (id, body = {}) => postJson(`/api/plans/${encodeURIComponent(id)}/what-if-review-level`, body),
  planBranchTemplates: (id) => fetchJson(`/api/plans/${encodeURIComponent(id)}/branch-templates`),
  updatePlanBranchTemplates: (id, body = {}) => putJson(`/api/plans/${encodeURIComponent(id)}/branch-templates`, body),
  planScenarioBranch: (id, body = {}) => postJson(`/api/plans/${encodeURIComponent(id)}/scenario-branch`, body),
  planSavedSimulations: (id, limit = 50) => fetchJson(`/api/plans/${encodeURIComponent(id)}/simulations/saved?limit=${encodeURIComponent(limit)}`),
  savePlanSimulation: (id, body = {}) => postJson(`/api/plans/${encodeURIComponent(id)}/simulations/saved`, body),
  planSavedSimulation: (id, savedSimulationId) => fetchJson(
    `/api/plans/${encodeURIComponent(id)}/simulations/saved/${encodeURIComponent(savedSimulationId)}`,
  ),
  comparePlanSavedSimulationCurrent: (id, savedSimulationId) => fetchJson(
    `/api/plans/${encodeURIComponent(id)}/simulations/saved/${encodeURIComponent(savedSimulationId)}/compare-current`,
  ),
  rerunPlanSavedSimulation: (id, savedSimulationId, body = {}) => postJson(
    `/api/plans/${encodeURIComponent(id)}/simulations/saved/${encodeURIComponent(savedSimulationId)}/rerun`,
    body,
  ),
  attachPlanSavedSimulationDecision: (id, savedSimulationId, body = {}) => postJson(
    `/api/plans/${encodeURIComponent(id)}/simulations/saved/${encodeURIComponent(savedSimulationId)}/decision`,
    body,
  ),
  planWithdrawalStrategyCompare: (id, body = {}) => postJson(`/api/plans/${encodeURIComponent(id)}/withdrawal-strategy-compare`, body),
  refreshPlanContext: (id) => postJson(`/api/plans/${encodeURIComponent(id)}/refresh-context`, {}),
  createPlan:   (body) => postJson('/api/plans', body),
  appendDecision: (id, body) => postJson(`/api/plans/${encodeURIComponent(id)}/decisions`, body),
  setActivePlan: (id) => postJson(`/api/plans/${encodeURIComponent(id)}/activate`, {}),
  holdings:     () => fetchJson('/api/portfolio/holdings'),
  portfolioLookThrough: () => fetchJson('/api/portfolio/look-through'),
  portfolioAnalytics: (opts = {}) => fetchJson(`/api/portfolio/analytics?${new URLSearchParams({
    limit: String(opts.limit || 180),
    top_n: String(opts.topN || opts.top_n || 5),
    period: opts.period || '1y',
    ...(opts.symbols ? { symbols: opts.symbols } : {}),
  }).toString()}`),
  portfolioAdd: (body = {}) => postJson('/api/portfolio/add', body),
  portfolioTransactions: (limit = 100) => fetchJson(`/api/portfolio/transactions?limit=${encodeURIComponent(limit)}`),
  addTransaction: (body = {}) => postJson('/api/portfolio/transactions', body),
  deletePortfolioTransaction: (id) => fetchJson(
    `/api/portfolio/transactions/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
  ),
  portfolioAccounts: () => fetchJson('/api/portfolio/accounts'),
  portfolioAudit: (limit = 25) => fetchJson(`/api/portfolio/audit?limit=${encodeURIComponent(limit)}`),
  portfolioExportBundle: (limit = 10000) => fetchJson(`/api/portfolio/export-bundle?limit=${encodeURIComponent(limit)}`),
  portfolioAssetSearch: (opts = {}) => fetchJson(portfolioAssetSearchUrl(opts)),
  portfolioAsset: (symbol) => fetchJson(`/api/portfolio/assets/${encodeURIComponent(symbol)}`),
  updatePortfolioAssetMetadata: (symbol, body = {}) => putJson(
    `/api/portfolio/assets/${encodeURIComponent(symbol)}/metadata`,
    body,
  ),
  portfolioCustomAssets: () => fetchJson('/api/portfolio/custom-assets'),
  createPortfolioCustomAsset: (body = {}) => postJson('/api/portfolio/custom-assets', body),
  portfolioManualPrices: () => fetchJson('/api/portfolio/manual-prices'),
  setPortfolioManualPrice: (body = {}) => putJson('/api/portfolio/manual-prices', body),
  clearPortfolioManualPrice: (symbol) => fetchJson(
    `/api/portfolio/manual-prices/${encodeURIComponent(symbol)}`,
    { method: 'DELETE' },
  ),
  portfolioFxRates: () => fetchJson('/api/portfolio/fx-rates'),
  setPortfolioFxRate: (body = {}) => putJson('/api/portfolio/fx-rates', body),
  clearPortfolioFxRate: (currency) => fetchJson(
    `/api/portfolio/fx-rates/${encodeURIComponent(currency)}`,
    { method: 'DELETE' },
  ),
  portfolioCostBasisMethods: () => fetchJson('/api/portfolio/cost-basis-methods'),
  portfolioRiskPolicy: () => fetchJson('/api/portfolio/risk-policy'),
  updatePortfolioRiskPolicy: (body = {}) => putJson('/api/portfolio/risk-policy', body),
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
  peerBenchmark: () => fetchJson('/api/peer-benchmark'),
  lifeInterview: () => fetchJson('/api/life-plans/interview'),
  lifePlanDrafts: (answers = {}) => postJson('/api/life-plans/drafts', { answers }),
  updateProfile: (body, opts = {}) => putJson(financialProfileUrl(opts), body),
  onboarding:   () => fetchJson('/api/onboarding/status'),
  onboardingProgress: () => fetchJson('/api/onboarding/progress'),
  startOnboarding: () => postJson('/api/onboarding/progress/start', {}),
  updateOnboardingProgress: (body = {}) => patchJson('/api/onboarding/progress', body),

  // User settings
  settings:       () => fetchJson('/api/settings'),
  updateSettings: (body = {}) => putJson('/api/settings', body),
  testLlmSettings: (body = {}) => postJson('/api/settings/test-llm', body),
  contextSettings: () => fetchJson('/api/settings/context'),
  testEmbeddingSettings: (body = {}) => postJson('/api/settings/test-embedding', body),
  llmUsage: () => fetchJson('/api/settings/llm-usage'),

  // Import & sync
  triggerSync:        () => postJson('/api/snapshot/sync', {}),
  importFiles:        () => fetchJson('/api/import/files'),
  csvTemplates:       () => fetchJson('/api/import/csv-templates'),
  importCsvUpload:    (formData) => postForm('/api/import/upload-csv', formData),
  uploadStatement:    (formData) => postForm('/api/import/statement', formData),
  uploadStatementImage: (formData) => postForm('/api/import/statement-vision', formData),
  profileDefaults:       () => fetchJson('/api/profile/defaults'),
  profileDocumentVision:      (formData) => postForm('/api/profile/document-vision', formData),
  applyProfileDocumentVision: (body = {}) => postJson('/api/profile/document-vision/apply', body),
  applyStatementSuggestions: (body = {}) => postJson('/api/import/statement/apply', body),
  importWorkbenchPreview: (formData) => postForm('/api/import/workbench/preview', formData),
  applyImportWorkbench: (sessionId, body = {}) => postJson(
    `/api/import/workbench/${encodeURIComponent(sessionId)}/apply`,
    body,
  ),
  importReports:      (limit = 20) => fetchJson(`/api/import/reports?limit=${encodeURIComponent(limit)}`),
  importReport:       (reportId) => fetchJson(`/api/import/reports/${encodeURIComponent(reportId)}`),

  // Workflows
  workflowTemplates:  () => fetchJson('/api/workflows/templates'),
  runWorkflow:        (body = {}) => postJson('/api/workflows/run', body),

  // Context intelligence
  contextCandidates: (opts = {}) => fetchJson(contextCandidatesUrl(opts)),
  updateContextCandidateLifecycle: (id, body = {}) => patchJson(
    `/api/context/candidates/${encodeURIComponent(id)}/lifecycle`,
    body,
  ),
  applyContextCandidate: (id) => postJson(`/api/context/candidates/${id}/apply`, {}),
  inferProfileCandidates: () => postJson('/api/context/candidates/infer-profile', {}),
  contextCandidateEvents: (id) => fetchJson(`/api/context/candidates/${encodeURIComponent(id)}/events`),

  // Copilot
  conversations:     (limit = 25, includeArchived = false) => fetchJson(
    `/api/copilot/conversations?limit=${limit}&include_archived=${includeArchived ? 'true' : 'false'}`,
  ),
  conversation:      (id) => fetchJson(`/api/copilot/conversations/${encodeURIComponent(id)}`),
  patchConversation: (id, body = {}) => patchJson(
    `/api/copilot/conversations/${encodeURIComponent(id)}`,
    body,
  ),
  patchConversationFocus: (id, body = {}) => patchJson(
    `/api/copilot/conversations/${encodeURIComponent(id)}/focus`,
    body,
  ),
  patchConversationLlm: (id, body = {}) => patchJson(
    `/api/copilot/conversations/${encodeURIComponent(id)}/llm`,
    body,
  ),
  llmOptions:        (conversationId) => fetchJson(
    conversationId
      ? `/api/copilot/llm-options?conversation_id=${encodeURIComponent(conversationId)}`
      : '/api/copilot/llm-options',
  ),
  focusDomains:      () => fetchJson('/api/copilot/focus/domains'),
  copilotChat:       (body) => postJson('/api/copilot/chat', body),
  copilotChatStream: (body, options = {}) => fetchSse('/api/copilot/chat/stream', body, options),

  // Recommendations
  recommendations: (opts) => fetchJson(recommendationsUrl(opts)),
  recommendation:  (id)   => fetchJson(`/api/recommendations/${encodeURIComponent(id)}`),
  preview:         (id, body = {}) => postJson(`/api/recommendations/${encodeURIComponent(id)}/preview`, body),
  apply:           (id, body = {}) => postJson(`/api/recommendations/${encodeURIComponent(id)}/apply`, body),
  reject:          (id, body = {}) => postJson(`/api/recommendations/${encodeURIComponent(id)}/reject`, body),
  archive:         (id, body = {}) => postJson(`/api/recommendations/${encodeURIComponent(id)}/archive`, body),
  outcome:         (id, body = {}) => postJson(`/api/recommendations/${encodeURIComponent(id)}/outcome`, body),
  outcomePrefill:  (id)            => fetchJson(`/api/recommendations/${encodeURIComponent(id)}/outcome/prefill`),
  closure:         (planId)        => fetchJson(planId ? `/api/recommendations/closure-analytics?plan_id=${encodeURIComponent(planId)}` : '/api/recommendations/closure-analytics'),
  sweepPreview:    (body = {})     => postJson('/api/recommendations/generate/run-all', { ...body, dry_run: true }),
  sweepCreate:     (body = {})     => postJson('/api/recommendations/generate/run-all', { ...body, dry_run: false }),
};
