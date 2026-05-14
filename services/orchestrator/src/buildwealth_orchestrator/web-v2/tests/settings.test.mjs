import test from 'node:test';
import assert from 'node:assert/strict';
import { toDraft, buildPayloadFor, parseTestError, demoWorkspaceCard, accountCard } from '../views/settings.js';

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
});
