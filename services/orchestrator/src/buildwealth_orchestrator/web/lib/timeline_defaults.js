export const TIMELINE_EVENT_TYPES = Object.freeze([
  'purchase',
  'windfall',
  'job_change',
  'retirement',
  'milestone',
]);

export const TIMELINE_IMPACT_TYPES = Object.freeze([
  'income',
  'expense',
  'portfolio',
  'contribution',
  'debt_payment',
]);

export const TIMELINE_FREQUENCIES = Object.freeze([
  'one_time',
  'monthly',
  'yearly',
]);

export const TIMELINE_DEFAULT_IMPACT_BY_EVENT = Object.freeze({
  purchase: 'expense',
  windfall: 'income',
  job_change: 'income',
  retirement: 'contribution',
  milestone: 'portfolio',
});
