import test from 'node:test';
import assert from 'node:assert/strict';
import { renderDataQuality } from '../views/profile/data_quality.js';

test('data quality: empty profile shows two reassuring empty cards', () => {
  const ui = { profile: { profile_metadata: {} }, candidates: [] };
  const markup = String(renderDataQuality(ui));
  assert.match(markup, /Pending review/);
  assert.match(markup, /Nothing pending/);
  assert.match(markup, /Confirmed sources/);
  assert.match(markup, /No fields have recorded sources yet/);
});

test('data quality: lists profile-targeted candidates with deep links', () => {
  const ui = {
    profile: { profile_metadata: {} },
    candidates: [
      {
        id: 'c1',
        target_domain: 'profile',
        target_area: 'tax_profile',
        target_field: 'marginal_tax_rate',
        extracted_claim: 'User said marginal rate is 32%',
        confidence: 'high',
        review_route: '#profile?section=taxes',
      },
      {
        // legacy candidate without target_domain — fall back to review_route
        id: 'c2',
        review_route: '#profile?section=investing',
        extracted_claim: 'Suggested cash cushion is 6 months',
        confidence: 'medium',
      },
      {
        // unrelated candidate that should NOT appear
        id: 'c3',
        target_domain: 'plan',
        review_route: '#plan',
        extracted_claim: 'Plan trajectory drift',
      },
    ],
  };
  const markup = String(renderDataQuality(ui));
  assert.match(markup, /User said marginal rate is 32%/);
  assert.match(markup, /Suggested cash cushion is 6 months/);
  assert.doesNotMatch(markup, /Plan trajectory drift/);
  // Deep links flow through to review_route
  assert.match(markup, /href="#profile\?section=taxes"/);
  assert.match(markup, /href="#profile\?section=investing"/);
});

test('data quality: renders confirmed metadata sorted with friendly labels', () => {
  const ui = {
    profile: {
      profile_metadata: {
        'tax_profile.state': {
          status: 'user_confirmed',
          source: 'profile_editor',
          confidence: 'high',
          updated_at: '2026-05-08T19:29:57Z',
          last_confirmed_at: '2026-05-08T19:29:57Z',
          confirmed_by_user: true,
        },
        'investment_policy.minimum_cash_runway_months': {
          status: 'pending_review',
          source: 'copilot_chat',
          updated_at: '2026-05-01T12:00:00Z',
        },
      },
    },
    candidates: [],
  };
  const markup = String(renderDataQuality(ui));
  assert.match(markup, /State/);
  assert.match(markup, /Minimum cash cushion/);
  assert.match(markup, /Confirmed/);
  assert.match(markup, /Pending review/);
  // Source name is humanized (underscores → spaces)
  assert.match(markup, /profile editor/);
  assert.match(markup, /copilot chat/);
});
