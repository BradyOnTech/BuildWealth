// Context capture lane — reviewed memory before it can shape answers.

import { html, raw, stripHtml } from '../../lib/dom.js';
import { fmtPct, fmtRelative, fmtUsd, roman } from '../../lib/format.js';

export const CONTEXT_CAPTURE_STATES = [
  { key: 'pending_review', label: 'pending review' },
  { key: 'deferred', label: 'later' },
  { key: 'stale_unconfirmed', label: 'needs refresh' },
  { key: 'applied', label: 'remembered' },
  { key: 'rejected', label: 'rejected' },
  { key: 'all', label: 'all' },
];

const TERMINAL_STATES = new Set(['applied', 'rejected', 'superseded', 'archived']);
const SOURCE_REVIEW_DOMAINS = new Set(['profile', 'plan', 'research', 'recommendation', 'import']);
const PROFILE_APPLY_FIELD_PREFIXES = ['tax_profile.', 'investment_policy.'];

// Candidates the apply bridge can write straight into the financial profile.
export function canApplyToProfile(candidate) {
  const patchKind = String(candidate?.metadata?.profile_patch_kind || '').trim();
  if (patchKind) return true;
  const field = String(candidate?.target_field || '').trim();
  return PROFILE_APPLY_FIELD_PREFIXES.some(prefix => field.startsWith(prefix));
}

export function renderContextCaptures(ctx = {}) {
  const items = Array.isArray(ctx.items) ? ctx.items : [];
  const lifecycleState = ctx.lifecycleState || 'pending_review';

  // Nothing waiting on the default lane collapses to one quiet line — the
  // lane browser stays one click away instead of holding a screen of empty.
  if (!items.length && !ctx.busy && !ctx.error && lifecycleState === 'pending_review') {
    return html`
      <section class="context-captures quiet" aria-labelledby="context-captures-title">
        <span class="section-eyebrow" id="context-captures-title">Context capture</span>
        ${ctx.confirmation ? html`<p class="quality-quote context-capture-confirmation">${ctx.confirmation}</p>` : ''}
        <details class="diagnostics-toggle">
          <summary>Nothing needs a decision — browse past captures</summary>
          <div class="inbox-filters context-capture-filters">
            <div class="filter-chips" role="tablist" aria-label="Context capture status">
              ${raw(CONTEXT_CAPTURE_STATES.map(state => contextStateChip(state, state.key === lifecycleState)).join(''))}
            </div>
          </div>
        </details>
      </section>
    `;
  }

  const body = ctx.busy && !items.length
    ? html`<div class="skeleton" style="height: 180px;">.</div>`
    : renderContextCaptureBody(items, ctx);

  return html`
    <section class="context-captures" aria-labelledby="context-captures-title">
      <header class="context-captures-header">
        <div>
          <span class="section-eyebrow">Context capture</span>
          <h3 class="context-captures-title" id="context-captures-title">Context that needs a decision.</h3>
        </div>
        <p class="context-captures-count">
          ${items.length} ${items.length === 1 ? 'capture' : 'captures'}
        </p>
      </header>
      <div class="inbox-filters context-capture-filters">
        <div class="filter-chips" role="tablist" aria-label="Context capture status">
          ${raw(CONTEXT_CAPTURE_STATES.map(state => contextStateChip(state, state.key === lifecycleState)).join(''))}
        </div>
      </div>
      ${ctx.error ? html`<p class="error-banner">${ctx.error}</p>` : ''}
      ${ctx.confirmation ? html`<p class="quality-quote context-capture-confirmation">${ctx.confirmation}</p>` : ''}
      ${raw(body)}
    </section>
  `;
}

function renderContextCaptureBody(items, ctx) {
  if (!items.length) {
    return html`
      <div class="empty-block context-captures-empty">
        <span class="glyph">¶</span>
        <p>${emptyMessageFor(ctx.lifecycleState)}</p>
      </div>
    `;
  }
  return html`
    <ol class="entry-list context-capture-list">
      ${raw(items.map((candidate, index) => renderContextCandidate(candidate, index + 1, ctx)).join(''))}
    </ol>
  `;
}

function contextStateChip(state, active) {
  return html`
    <button class="chip" data-context-state="${state.key}" aria-pressed="${active}">
      ${state.label}
    </button>
  `;
}

function renderContextCandidate(candidate, index, ctx) {
  const id = String(candidate?.id || '').trim();
  const state = String(candidate?.lifecycle_state || 'pending_review').trim().toLowerCase();
  const expanded = ctx.expanded && ctx.expanded.id === id ? ctx.expanded : null;
  const route = reviewRoute(candidate);
  const targetLine = targetSummary(candidate);
  const sourceLine = sourceSummary(candidate);
  const readiness = plainText(candidate?.action_readiness);
  const updated = candidate?.updated_at ? fmtRelative(candidate.updated_at) : '';

  return html`
    <li class="entry context-capture-entry" data-candidate-id="${id}">
      <span class="entry-numeral">${roman(index)}.</span>
      <div class="entry-body">
        <div class="entry-tag context-capture-tags">
          <span class="status-pill ${stateLabelClass(state)}">
            <span class="dot"></span>${stateLabel(state)}
          </span>
          ${readiness ? html`<span class="entry-tag">${readiness}</span>` : ''}
          ${route.label ? html`<span class="entry-tag">${route.label}</span>` : ''}
          ${updated ? html`<span class="entry-tag">${updated}</span>` : ''}
        </div>
        <h3 class="entry-title context-capture-title">${captureTitle(candidate)}</h3>
        <p class="entry-rationale">${plainText(candidate?.extracted_claim) || 'No claim text was captured.'}</p>
        <dl class="context-capture-facts">
          ${targetLine ? html`<div><dt>Would update</dt><dd>${targetLine}</dd></div>` : ''}
          ${sourceLine ? html`<div><dt>Captured from</dt><dd>${sourceLine}</dd></div>` : ''}
        </dl>
        ${state === 'pending_review' ? html`
          <p class="marginalia context-capture-note">Not used as financial truth yet.</p>
        ` : ''}
        ${raw(renderCandidateActions(candidate, { expanded, actionBusyId: ctx.actionBusyId }))}
        ${expanded ? raw(renderExpanded(candidate, expanded)) : ''}
      </div>
    </li>
  `;
}

function renderCandidateActions(candidate, { expanded, actionBusyId } = {}) {
  const id = String(candidate?.id || '').trim();
  const state = String(candidate?.lifecycle_state || '').trim().toLowerCase();
  if (!id || TERMINAL_STATES.has(state)) return '';

  const busy = actionBusyId === id;
  const disabled = busy ? 'disabled' : '';
  const route = reviewRoute(candidate);
  const routeHref = routeHrefFor(candidate);
  const sourceReview = requiresSourceReview(candidate);
  const expandedMode = expanded?.mode || '';
  const profileApply = canApplyToProfile(candidate);

  return html`
    <div class="entry-actions context-capture-actions">
      ${profileApply ? html`
        <button class="action-link" data-context-action="apply-to-profile" data-candidate-id="${id}" ${disabled}>
          Apply to Profile <span class="arrow">›</span>
        </button>
      ` : ''}
      ${sourceReview ? html`
        <a class="action-link" href="${routeHref}">
          Review ${route.label || 'source'} <span class="arrow">→</span>
        </a>
        <button class="action-link" data-context-expand="resolve" data-candidate-id="${id}"
          aria-expanded="${expandedMode === 'resolve'}" ${disabled}>
          Resolve <span class="arrow">›</span>
        </button>
      ` : html`
        <button class="action-link" data-context-action="remember" data-candidate-id="${id}" ${disabled}>
          Remember this <span class="arrow">›</span>
        </button>
      `}
      <button class="action-link muted" data-context-action="defer" data-candidate-id="${id}" ${disabled}>
        Later <span class="arrow">›</span>
      </button>
      <button class="action-link danger" data-context-action="reject" data-candidate-id="${id}" ${disabled}>
        Not true <span class="arrow">›</span>
      </button>
      <button class="action-link muted" data-context-expand="explain" data-candidate-id="${id}"
        aria-expanded="${expandedMode === 'explain'}" ${disabled}>
        Explain <span class="arrow">›</span>
      </button>
    </div>
  `;
}

function renderExpanded(candidate, expanded) {
  if (expanded.mode === 'resolve') return renderResolveForm(candidate, expanded);
  if (expanded.mode === 'explain') return renderExplainPanel(candidate, expanded);
  return '';
}

function renderResolveForm(candidate, expanded) {
  const id = String(candidate?.id || '').trim();
  const route = reviewRoute(candidate);
  const label = route.label || 'source';
  return html`
    <div class="inline-form context-capture-form" data-context-form="resolve" data-candidate-id="${id}">
      <p class="inline-form-title">Finish after source review</p>
      <p class="marginalia">Use these after ${label} has the right value, or after you decide the current ${label} should stay as-is.</p>
      <div class="inline-form-row">
        <label class="inline-label" for="context-note-${id}">Note (optional)</label>
        <textarea id="context-note-${id}" name="review_note"
          placeholder="What did you confirm or change?"></textarea>
      </div>
      ${expanded.error ? html`<p class="inline-warning">${expanded.error}</p>` : ''}
      <div class="inline-form-actions">
        <button class="btn btn-primary" data-context-resolution="source_updated" data-candidate-id="${id}" ${expanded.busy ? 'disabled' : ''}>
          I updated ${label}
        </button>
        <button class="btn btn-ghost" data-context-resolution="current_source" data-candidate-id="${id}" ${expanded.busy ? 'disabled' : ''}>
          Use current ${label}
        </button>
        <button class="btn btn-quiet" data-context-cancel data-candidate-id="${id}" ${expanded.busy ? 'disabled' : ''}>Cancel</button>
      </div>
    </div>
  `;
}

function renderExplainPanel(candidate, expanded) {
  const id = String(candidate?.id || '').trim();
  const route = reviewRoute(candidate);
  const rationale = plainText(candidate?.materiality_rationale);
  const reason = plainText(route.reason);
  const readiness = plainText(candidate?.action_readiness);
  return html`
    <div class="inline-form muted context-capture-form" data-context-form="explain" data-candidate-id="${id}">
      <p class="inline-form-title">Why this is paused</p>
      <p class="marginalia">
        BuildWealth noticed this context, but it has not been saved into ${route.label || 'the right source'}.
        ${reason}
      </p>
      ${rationale ? html`<p class="context-capture-explanation">${rationale}</p>` : ''}
      ${readiness ? html`<p class="context-capture-explanation">${readiness}. Until reviewed, Copilot treats it as unconfirmed.</p>` : ''}
      ${expanded.error ? html`<p class="inline-warning">${expanded.error}</p>` : ''}
      <div class="inline-form-actions">
        <button class="btn btn-ghost" data-context-cancel data-candidate-id="${id}" ${expanded.busy ? 'disabled' : ''}>Close</button>
      </div>
    </div>
  `;
}

function captureTitle(candidate) {
  const field = humanField(candidate?.target_field || candidate?.target_area);
  const domain = humanText(candidate?.target_domain || 'context');
  return `Capture for ${field || domain}`;
}

function targetSummary(candidate) {
  const field = humanField(candidate?.target_field || candidate?.target_area);
  const value = formatTargetValue(candidate?.target_value, candidate?.target_field);
  if (field && value) return `${field}: ${value}`;
  return field || value;
}

function sourceSummary(candidate) {
  const sourceDomain = humanText(candidate?.source_domain);
  const sourceRef = plainText(candidate?.source_ref);
  if (sourceDomain && sourceRef) return `${sourceDomain} · ${sourceRef}`;
  return sourceDomain || sourceRef;
}

function routeHrefFor(candidate) {
  const route = reviewRoute(candidate);
  const routeName = String(route.route || '').trim().toLowerCase();
  const target = String(route.target || '').trim();
  if (routeName === 'profile') return '/#profile';
  if (routeName === 'plan') {
    const section = target && target !== 'plan_workspace' ? `?section=${encodeURIComponent(target)}` : '';
    return `#plan${section}`;
  }
  if (routeName === 'research') return '#research';
  if (routeName === 'inbox') return '#inbox';
  if (routeName === 'import') return '#atelier';
  return `#copilot?focus=${encodeURIComponent(String(candidate?.id || ''))}&intent=context-candidate`;
}

function requiresSourceReview(candidate) {
  const targetDomain = String(candidate?.target_domain || '').trim().toLowerCase();
  const routeName = String(reviewRoute(candidate).route || '').trim().toLowerCase();
  return SOURCE_REVIEW_DOMAINS.has(targetDomain) || SOURCE_REVIEW_DOMAINS.has(routeName);
}

function reviewRoute(candidate) {
  const route = candidate?.review_route && typeof candidate.review_route === 'object'
    ? candidate.review_route
    : {};
  return {
    route: String(route.route || 'copilot').trim().toLowerCase(),
    label: plainText(route.label || humanText(route.route || 'Copilot')),
    target: String(route.target || '').trim(),
    reason: route.reason,
  };
}

function formatTargetValue(value, field = '') {
  if (value == null || value === '') return '';
  const fieldText = String(field || '').toLowerCase();
  if (typeof value === 'number' && Number.isFinite(value)) {
    if (fieldText.includes('rate') || fieldText.includes('pct') || fieldText.includes('percent')) {
      return fmtPct(value, { fromFraction: Math.abs(value) <= 1 });
    }
    if (fieldText.includes('usd') || fieldText.includes('amount') || fieldText.includes('value')) {
      return fmtUsd(value);
    }
    return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value);
  }
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (Array.isArray(value)) return value.map(formatTargetValue).filter(Boolean).join(', ');
  if (typeof value === 'object') {
    if (value.summary) return plainText(value.summary);
    if (value.message_count != null) return `${value.message_count} messages summarized`;
    return Object.entries(value)
      .slice(0, 3)
      .map(([key, rawValue]) => `${humanField(key)}: ${formatTargetValue(rawValue)}`)
      .join(' · ');
  }
  return plainText(value);
}

function emptyMessageFor(state) {
  if (state === 'pending_review') return 'No pending context captures.';
  if (state === 'deferred') return 'No context captures are waiting for later.';
  if (state === 'stale_unconfirmed') return 'No stale captures need refresh.';
  if (state === 'applied') return 'No remembered captures yet.';
  if (state === 'rejected') return 'No rejected captures.';
  return 'No context captures match this filter.';
}

function stateLabel(state) {
  const match = CONTEXT_CAPTURE_STATES.find(item => item.key === state);
  if (match) return match.label;
  if (state === 'superseded') return 'source kept';
  if (state === 'archived') return 'archived';
  return humanText(state || 'pending review');
}

function stateLabelClass(state) {
  if (state === 'pending_review') return 'pending';
  if (state === 'stale_unconfirmed') return 'stale';
  return state || 'pending';
}

function humanField(value) {
  return humanText(value)
    .split(' ')
    .filter(Boolean)
    .map((part, index) => index === 0 ? capitalize(part) : part)
    .join(' ');
}

function humanText(value) {
  return plainText(value).replace(/[_.-]/g, ' ').replace(/\s+/g, ' ').trim();
}

function plainText(value) {
  return stripHtml(value == null ? '' : String(value)).trim();
}

function capitalize(value) {
  const text = String(value || '');
  return text ? text[0].toUpperCase() + text.slice(1) : '';
}
