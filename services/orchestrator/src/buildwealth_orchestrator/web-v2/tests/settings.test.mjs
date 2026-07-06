import test from 'node:test';
import assert from 'node:assert/strict';
import {
  toDraft,
  buildPayloadFor,
  parseTestError,
  demoWorkspaceCard,
  accountCard,
  accountDataDeletionPanel,
  hostedReadinessPanel,
  usageCard,
} from '../views/settings.js';

test('toDraft: reads provider settings with sensible defaults', () => {
  const draft = toDraft({
    llm_provider: 'anthropic',
    llm_api_key: '••••••••abcd',
    llm_model: 'claude-opus-4-7',
    llm_base_url: 'https://api.anthropic.com/v1',
    llm_max_tokens: 4096,
    llm_timeout_seconds: 90,
    llm_parallel_tool_calls: false,
  });
  assert.equal(draft.llm_provider, 'anthropic');
  assert.equal(draft.llm_api_key, '••••••••abcd');
  assert.equal(draft.llm_max_tokens, 4096);
  assert.equal(draft.llm_timeout_seconds, 90);
  assert.equal(draft.llm_parallel_tool_calls, false);
});

test('usageCard renders monthly spend rows and hides when empty', () => {
  const markup = String(usageCard({
    month: '2026-07',
    current: {
      rows: [
        { provider: 'openai', model: 'gpt-5.5', task: 'chat', requests: 14, prompt_tokens: 182000, completion_tokens: 24000, estimated_cost_usd: 0.4675 },
        { provider: 'custom_openai_compatible', model: 'llama3.2', task: 'summarize', requests: 40, prompt_tokens: 900000, completion_tokens: 120000, estimated_cost_usd: 0 },
      ],
      requests: 54,
      prompt_tokens: 1082000,
      completion_tokens: 144000,
      estimated_cost_usd: 0.4675,
    },
  }));
  assert.match(markup, /AI usage · 2026-07/);
  assert.match(markup, /~\$0\.47 estimated across 54 requests/);
  assert.match(markup, /gpt-5\.5 · 182,000 in \/ 24,000 out/);
  assert.match(markup, /free \/ local/);
  assert.match(markup, /nothing leaves the machine/);

  assert.equal(String(usageCard(null)), '');
  assert.equal(String(usageCard({ month: '2026-07', current: { rows: [] } })), '');
});

test('toDraft/buildPayloadFor: task routing keys round-trip', () => {
  const draft = toDraft({
    llm_provider: 'anthropic',
    llm_task_summarize_provider: 'custom_openai_compatible',
    llm_task_summarize_model: 'llama3.2',
    llm_task_summarize_base_url: 'http://localhost:11434/v1',
  });
  assert.equal(draft.llm_task_summarize_provider, 'custom_openai_compatible');
  assert.equal(draft.llm_task_summarize_model, 'llama3.2');
  assert.equal(draft.llm_task_summarize_base_url, 'http://localhost:11434/v1');

  const payload = buildPayloadFor({ draft, apiKeyDirty: false, loadedSettings: {} });
  assert.equal(payload.llm_task_summarize_provider, 'custom_openai_compatible');
  assert.equal(payload.llm_task_summarize_model, 'llama3.2');
  assert.equal(payload.llm_task_summarize_base_url, 'http://localhost:11434/v1');

  // Unset routing stays empty (= inherit), never undefined.
  const inherit = buildPayloadFor({ draft: toDraft({}), apiKeyDirty: false, loadedSettings: {} });
  assert.equal(inherit.llm_task_summarize_provider, '');
});

test('toDraft: fills missing fields with defaults', () => {
  const draft = toDraft({});
  assert.equal(draft.llm_provider, 'openai');
  assert.equal(draft.llm_api_key, '');
  assert.equal(draft.llm_max_tokens, 2048);
  assert.equal(draft.llm_timeout_seconds, 60);
  assert.equal(draft.llm_parallel_tool_calls, true);
});

test('buildPayloadFor: round-trips masked API key when user has not typed over it', () => {
  const loadedSettings = {
    llm_provider: 'openai',
    llm_api_key: '••••••••wxyz',
    llm_model: 'gpt-5.5',
    llm_base_url: 'https://api.openai.com/v1',
  };
  const draft = toDraft(loadedSettings);
  const payload = buildPayloadFor({ draft, apiKeyDirty: false, loadedSettings });
  // Server's UserSettingsStore.save preserves the stored value when the
  // payload key is the masked string — so the masked value must round-trip.
  assert.equal(payload.llm_api_key, '••••••••wxyz');
  assert.equal(payload.llm_provider, 'openai');
  assert.equal(payload.llm_model, 'gpt-5.5');
});

test('buildPayloadFor: sends the new key when the user has typed over it', () => {
  const loadedSettings = { llm_api_key: '••••••••wxyz' };
  const draft = toDraft({ llm_provider: 'openai' });
  draft.llm_api_key = 'sk-real-secret';
  const payload = buildPayloadFor({ draft, apiKeyDirty: true, loadedSettings });
  assert.equal(payload.llm_api_key, 'sk-real-secret');
});

test('buildPayloadFor: empty saved key sends empty string', () => {
  const draft = toDraft({});
  const payload = buildPayloadFor({ draft, apiKeyDirty: false, loadedSettings: {} });
  assert.equal(payload.llm_api_key, '');
});

test('parseTestError: prefers a structured detail attached to the error', () => {
  const err = new Error('Request to /api/settings/test-llm failed with 502');
  err.detail = {
    ok: false,
    provider: 'openai',
    model: 'gpt-5.5',
    stage: 'provider_http_error',
    detail: 'Bad Gateway',
  };
  const parsed = parseTestError(err);
  assert.equal(parsed.ok, false);
  assert.equal(parsed.provider, 'openai');
  assert.equal(parsed.stage, 'provider_http_error');
  assert.equal(parsed.detail, 'Bad Gateway');
});

test('parseTestError: falls back to a plain failure shape when detail is absent', () => {
  const parsed = parseTestError(new Error('Network down'));
  assert.equal(parsed.ok, false);
  assert.equal(parsed.stage, 'provider_error');
  assert.equal(parsed.detail, 'Network down');
});

test('demoWorkspaceCard: renders reset action for demo workspace', () => {
  const markup = String(demoWorkspaceCard({
    workspaces: [
      { id: 'ws_real', name: 'My Household', workspace_type: 'household', is_demo: false },
      { id: 'ws_demo', name: 'Demo Household', workspace_type: 'demo', is_demo: true },
    ],
    activeWorkspaceId: 'ws_real',
    demoResetting: false,
  }));
  assert.match(markup, /Demo workspace/);
  assert.match(markup, /Reset demo data/);
  assert.match(markup, /Switch to demo/);
});

test('demoWorkspaceCard: labels active demo workspace clearly', () => {
  const markup = String(demoWorkspaceCard({
    workspaces: [{ id: 'ws_demo', name: 'Demo Household', workspace_type: 'demo', is_demo: true }],
    activeWorkspaceId: 'ws_demo',
    demoResetting: false,
  }));
  assert.match(markup, /Active now/);
  assert.match(markup, /disabled/);
});

test('accountCard: exposes export password and deactivation controls', () => {
  const markup = String(accountCard({
    accountExporting: false,
    passwordChanging: false,
    deactivateBusy: false,
    accountExportResult: {
      exported_at: '2026-05-14T12:00:00Z',
      workspaces: [{ id: 'ws_1' }],
      audit_events: [{ action: 'auth.login' }],
    },
  }));
  assert.match(markup, /Account &amp; data/);
  assert.match(markup, /Prepare account export/);
  assert.match(markup, /Change password/);
  assert.match(markup, /Deactivate account/);
  assert.match(markup, /Account export ready/);
  assert.match(markup, /Delete BuildWealth data/);
  assert.match(markup, /Preview deletion/);
});

test('accountCard: keeps hosted sign-in security provider managed', () => {
  const markup = String(accountCard({
    session: { user: { auth_provider: 'Test OIDC' } },
    authConfig: {
      account_management_url: 'https://identity.example.test/account',
      password_reset_url: 'https://identity.example.test/reset',
      mfa_enrollment_url: 'https://identity.example.test/mfa',
      passkey_enrollment_url: 'https://identity.example.test/passkeys',
    },
    accountExporting: false,
    passwordChanging: false,
    deactivateBusy: false,
  }));

  assert.match(markup, /Sign-in security is managed by Test OIDC/);
  assert.match(markup, /password reset, multi-factor sign-in, and passkeys/);
  assert.match(markup, /Account security/);
  assert.match(markup, /Set up passkeys/);
  assert.match(markup, /Type close buildwealth access/);
  assert.match(markup, /Close BuildWealth access/);
  assert.match(markup, /Delete BuildWealth data/);
  assert.doesNotMatch(markup, /Change password/);
  assert.doesNotMatch(markup, /Deactivate account/);
});

test('accountDataDeletionPanel: renders preview summary and pending cancel control', () => {
  const markup = String(accountDataDeletionPanel({
    accountDeletionScope: 'household',
    accountDeletionPreview: {
      scope: 'household',
      can_request: true,
      affected_workspace_count: 2,
      recovery_window_days: 30,
      purge_after: '2026-06-13T12:00:00Z',
      confirmation_phrase: 'delete household data',
      totals: {
        workspace_count: 2,
        file_count: 42,
        size_bytes: 1536,
        secret_count: 2,
        backup_archive_count: 3,
      },
      will_retain: ['minimal audit events', 'hosted identity provider account unless deleted by the provider'],
    },
    accountDeletionRequests: [
      {
        id: 'del_123',
        status: 'pending',
        scope: 'household',
        purge_after: '2026-06-13T12:00:00Z',
        preview: { affected_workspace_count: 2 },
      },
    ],
  }));

  assert.match(markup, /Delete BuildWealth data/);
  assert.match(markup, /2 workspaces/);
  assert.match(markup, /1.5 KB/);
  assert.match(markup, /2 secret keys/);
  assert.match(markup, /3 backup archives/);
  assert.match(markup, /Type delete household data/);
  assert.match(markup, /Schedule deletion/);
  assert.match(markup, /Household deletion pending/);
  assert.match(markup, /Cancel/);
});

test('hostedReadinessPanel: renders blockers in plain language', () => {
  const markup = String(hostedReadinessPanel({
    status: 'blocked',
    provider: 'Auth0',
    checks: [
      { id: 'auth_mode', status: 'ready', summary: 'Hosted auth mode is enabled.' },
      { id: 'client_id', status: 'blocked', summary: 'AUTH_OIDC_CLIENT_ID is required for hosted sign-in.' },
      { id: 'mfa_policy', status: 'warning', summary: 'MFA is encouraged but not required.' },
    ],
  }));

  assert.match(markup, /Auth0 has setup blockers/);
  assert.match(markup, /1 ready · 1 warning · 1 blocker/);
  assert.match(markup, /AUTH_OIDC_CLIENT_ID is required/);
  assert.match(markup, /MFA is encouraged/);
});

test('accountCard: includes hosted readiness for provider-managed sign-in', () => {
  const markup = String(accountCard({
    session: { user: { auth_provider: 'Auth0' } },
    authConfig: {},
    hostedReadiness: {
      status: 'ready',
      provider: 'Auth0',
      checks: [
        { id: 'metadata', status: 'ready', summary: 'OIDC metadata is available.' },
      ],
    },
    accountExporting: false,
    passwordChanging: false,
    deactivateBusy: false,
  }));

  assert.match(markup, /Sign-in security is managed by Auth0/);
  assert.match(markup, /Auth0 is ready for browser testing/);
  assert.match(markup, /1 ready · 0 warnings · 0 blockers/);
});
