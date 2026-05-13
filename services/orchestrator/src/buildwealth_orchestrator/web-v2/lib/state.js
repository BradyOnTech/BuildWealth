// Tiny shared state container for v2. No framework, no proxies — just an object.
// Views can read/write; an event bus lets cross-view subscriptions stay quiet.

export const state = {
  today: null,
  engines: null,
  telemetry: null,
  plans: [],
  activePlanId: null,
  session: null,
  workspaces: [],
  activeWorkspaceId: null,
  authRequired: false,
  lastError: null,
  bootedAt: null,
};

const listeners = new Map();

export function on(event, fn) {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event).add(fn);
  return () => listeners.get(event)?.delete(fn);
}

export function emit(event, payload) {
  const subs = listeners.get(event);
  if (!subs) return;
  for (const fn of subs) {
    try { fn(payload); } catch (e) { console.error('[v2 state]', event, e); }
  }
}
