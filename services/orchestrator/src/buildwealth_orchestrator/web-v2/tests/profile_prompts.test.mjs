import test from 'node:test';
import assert from 'node:assert/strict';

const storage = new Map();
globalThis.window = globalThis.window || {
  sessionStorage: {
    getItem: key => storage.get(key) || '',
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: key => storage.delete(key),
  },
};

const { onboardingQuickReplies } = await import('../views/copilot.js');
const { renderNextQuestion } = await import('../views/today.js');

const readiness = (sections) => ({ sections });

test('quick replies: household composition chips come first', () => {
  const status = {
    steps: [{ key: 'tax_profile', title: 'Tax profile', status: 'incomplete' }],
    profile_readiness: readiness([{ key: 'household', status: 'incomplete' }]),
  };
  const replies = onboardingQuickReplies(status);
  assert.ok(replies.length >= 3);
  assert.match(replies[0].message, /just me/i);
  assert.ok(replies.every(reply => reply.label && reply.message));
});

test('quick replies: tax step offers filing statuses and an estimate escape hatch', () => {
  const status = {
    steps: [{ key: 'tax_profile', title: 'Tax profile', status: 'incomplete' }],
    profile_readiness: readiness([{ key: 'household', status: 'complete' }]),
  };
  const replies = onboardingQuickReplies(status);
  assert.ok(replies.some(reply => /married filing jointly/i.test(reply.message)));
  assert.ok(replies.some(reply => /estimate it from my income/i.test(reply.message)));
});

test('quick replies: none when nothing enum-shaped is next', () => {
  const status = {
    steps: [{ key: 'income', title: 'Income profile', status: 'incomplete' }],
    profile_readiness: readiness([{ key: 'household', status: 'complete' }]),
  };
  assert.deepEqual(onboardingQuickReplies(status), []);
});

test('next question card names the payoff and links both paths', () => {
  const markup = String(renderNextQuestion(readiness([
    { key: 'household', status: 'complete', title: 'Household', detail: 'done' },
    { key: 'tax_profile', status: 'incomplete', title: 'Tax profile', detail: 'Add filing status and marginal rate.' },
  ])));
  assert.match(markup, /One answer unlocks/);
  assert.match(markup, /Roth ladder and loss-harvesting/);
  assert.match(markup, /#copilot\?intent=profile-setup/);
  assert.match(markup, /#profile\?section=taxes/);
});

test('next question card hides when the profile is complete', () => {
  const markup = String(renderNextQuestion(readiness([
    { key: 'household', status: 'complete' },
    { key: 'tax_profile', status: 'complete' },
  ])));
  assert.equal(markup, '');
});
