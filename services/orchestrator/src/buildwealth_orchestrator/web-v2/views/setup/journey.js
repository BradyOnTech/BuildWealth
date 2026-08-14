// SETUP · journey derivation (pure).
//
// Journey progress and financial readiness are deliberately separate concerns:
// advancing or skipping a step moves the journey, and never claims the evidence
// behind that step exists. `evidenceReady` is derived only from server payloads.

import { isEmptyWorkspace } from '../today.js';

export const SETUP_STEPS = [
  {
    id: 'welcome',
    numeral: 'I',
    short: 'Welcome',
    title: 'Start with a private household workspace.',
    lede: 'BuildWealth needs enough context to make the first picture useful—not every detail of your financial life.',
  },
  {
    id: 'foundation',
    numeral: 'II',
    short: 'Foundation',
    title: 'Give the numbers their household context.',
    lede: 'Who is in the household, what comes in, what usually goes out, and whether debt needs a place in the plan.',
  },
  {
    id: 'portfolio',
    numeral: 'III',
    short: 'What you own',
    title: 'Bring in the accounts that shape today.',
    lede: 'A statement is fastest, but current balances are enough for a first allocation and net-worth picture.',
  },
  {
    id: 'future',
    numeral: 'IV',
    short: 'What is ahead',
    title: 'Name one thing the money needs to make possible.',
    lede: 'A goal or life event gives the first forecast a direction. It can stay rough and change later.',
  },
  {
    id: 'first_picture',
    numeral: 'V',
    short: 'First picture',
    title: 'See what the current evidence can support.',
    lede: 'BuildWealth shows the useful numbers now and names what still needs evidence before you rely on the plan.',
  },
];

export function deriveSetupJourney({ progress, onboarding, today = null, health = null } = {}) {
  // Coalesce rather than rely on destructuring defaults: those only fire on
  // `undefined`, and both of these arrive as `null` before the first load
  // resolves and after a failed one.
  progress = progress || {};
  onboarding = onboarding || {};
  const currentId = SETUP_STEPS.some(step => step.id === progress.current_step)
    ? progress.current_step
    : SETUP_STEPS[0].id;
  const completed = new Set(Array.isArray(progress.completed_steps) ? progress.completed_steps : []);
  const skipped = new Set(Array.isArray(progress.skipped_steps) ? progress.skipped_steps : []);
  const sections = Array.isArray(onboarding?.profile_readiness?.sections)
    ? onboarding.profile_readiness.sections
    : [];
  const bySection = new Map(sections.map(section => [section.key, section]));
  const onboardingSteps = new Map(
    (Array.isArray(onboarding?.steps) ? onboarding.steps : []).map(step => [step.id, step]),
  );
  const foundationKeys = ['household', 'income', 'expenses', 'debt'];
  const foundationReady = foundationKeys.every(key => bySection.get(key)?.status === 'complete');
  const portfolioReady = ['complete', 'attention'].includes(onboardingSteps.get('snapshot')?.status);
  const futureReady = bySection.get('goals')?.status === 'complete';
  const firstPictureReady = Boolean(today || health) && !isEmptyWorkspace(today || {}, health);
  const evidence = {
    welcome: true,
    foundation: foundationReady,
    portfolio: portfolioReady,
    future: futureReady,
    first_picture: firstPictureReady,
  };

  return SETUP_STEPS.map((step, index) => ({
    ...step,
    index,
    current: step.id === currentId,
    completed: completed.has(step.id),
    skipped: skipped.has(step.id),
    evidenceReady: Boolean(evidence[step.id]),
  }));
}
