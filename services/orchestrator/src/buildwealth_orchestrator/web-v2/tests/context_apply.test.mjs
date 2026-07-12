import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { renderContextCaptures, canApplyToProfile } from '../views/inbox/context-captures.js';
import { api } from '../lib/api.js';

const currentDir = dirname(fileURLToPath(import.meta.url));
const read = (path) => readFileSync(resolve(currentDir, path), 'utf8');

test('api exposes context candidate apply + profile inference endpoints', async (t) => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  await api.applyContextCandidate('cand-1');
  await api.inferProfileCandidates();

  assert.equal(calls[0].url, '/api/context/candidates/cand-1/apply');
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(calls[1].url, '/api/context/candidates/infer-profile');
  assert.equal(calls[1].options.method, 'POST');
});

test('canApplyToProfile keys off patch kind and profile field prefixes', () => {
  assert.equal(canApplyToProfile({ metadata: { profile_patch_kind: 'income_items' } }), true);
  assert.equal(canApplyToProfile({ target_field: 'tax_profile.marginal_tax_rate' }), true);
  assert.equal(canApplyToProfile({ target_field: 'investment_policy.risk_tolerance' }), true);
  assert.equal(canApplyToProfile({ target_field: 'timeline.retirement.target_retirement_age' }), false);
  assert.equal(canApplyToProfile({ metadata: {} }), false);
});

test('context captures render Apply to Profile for eligible candidates', () => {
  const candidate = (overrides = {}) => ({
    id: 'ctx-1',
    lifecycle_state: 'pending_review',
    extracted_claim: 'My marginal tax rate is 32%.',
    target_domain: 'profile',
    target_area: 'tax_profile',
    target_field: 'tax_profile.marginal_tax_rate',
    target_value: 0.32,
    review_route: { route: 'profile', label: 'Profile' },
    metadata: {},
    ...overrides,
  });

  const eligible = String(renderContextCaptures({
    items: [candidate()],
    lifecycleState: 'pending_review',
  }));
  assert.match(eligible, /data-context-action="apply-to-profile"/);
  assert.match(eligible, /Apply to Profile/);
  // Existing actions stay in place.
  assert.match(eligible, /data-context-expand="resolve"/);
  assert.match(eligible, /data-context-action="defer"/);
  assert.match(eligible, /data-context-action="reject"/);

  const ineligible = String(renderContextCaptures({
    items: [candidate({
      target_domain: 'plan',
      target_area: 'timeline',
      target_field: 'timeline.retirement.target_retirement_age',
      target_value: 55,
      review_route: { route: 'plan', label: 'Plan' },
    })],
    lifecycleState: 'pending_review',
  }));
  assert.doesNotMatch(ineligible, /data-context-action="apply-to-profile"/);
});

test('context captures show the transient apply confirmation line', () => {
  const populated = String(renderContextCaptures({
    items: [],
    lifecycleState: 'all',
    confirmation: 'Set tax profile marginal tax rate to 32%.',
  }));
  assert.match(populated, /context-capture-confirmation/);
  assert.match(populated, /Set tax profile marginal tax rate to 32%\./);

  // The quiet empty lane keeps the confirmation visible too — applying the
  // last pending capture collapses the lane, but the receipt still shows.
  const quiet = String(renderContextCaptures({
    items: [],
    lifecycleState: 'pending_review',
    confirmation: 'Added 1 income item to the profile: Spouse income.',
  }));
  assert.match(quiet, /context-capture-confirmation/);
  assert.match(quiet, /Spouse income/);
});

test('inbox wires the apply-to-profile action through the api and refresh', () => {
  const source = read('../views/inbox.js');
  assert.match(source, /apply-to-profile/);
  assert.match(source, /api\.applyContextCandidate\(/);
  assert.match(source, /apply_result\?\.detail/);
  assert.match(source, /loadContextCaptures\(\)/);
});

test('sweep flow also triggers the profile inference sweep, tolerating failure', () => {
  const source = read('../views/inbox/sweep.js');
  assert.match(source, /api\.inferProfileCandidates\(\)\.catch\(/);
});

test('api.js keeps the two new context entries next to the lifecycle helper', () => {
  const source = read('../lib/api.js');
  assert.match(
    source,
    /applyContextCandidate: \(id\) => postJson\(`\/api\/context\/candidates\/\$\{id\}\/apply`, \{\}\),/,
  );
  assert.match(
    source,
    /inferProfileCandidates: \(\) => postJson\('\/api\/context\/candidates\/infer-profile', \{\}\),/,
  );
});
