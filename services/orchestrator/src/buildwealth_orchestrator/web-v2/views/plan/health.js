// Movement IB — Plan health.
// Client-derived confidence model for whether plan context is decision-grade.

import { html, raw, esc } from '../../lib/dom.js';

export function derivePlanHealth(plan = {}, state = {}) {
  const settings = plan.settings && typeof plan.settings === 'object' ? plan.settings : {};
  const recommendations = Array.isArray(state.recommendations) ? state.recommendations : [];
  const tracking = state.tracking && typeof state.tracking === 'object' ? state.tracking : null;
  const now = parseDate(state.now) || new Date();
  const signals = [];

  if (settings.marginal_tax_rate == null || settings.marginal_tax_rate === '') {
    signals.push({
      id: 'tax-assumptions',
      severity: 'weak',
      title: 'Tax assumptions need review',
      detail: 'Marginal tax rate is missing, so plan advice and investment-fit checks carry lower confidence.',
      href: planAssumptionsHref(plan),
    });
  }

  if (settings.annual_contribution_usd == null || Number(settings.annual_contribution_usd) <= 0) {
    signals.push({
      id: 'contribution-assumptions',
      severity: 'weak',
      title: 'Contribution assumptions need review',
      detail: 'Annual contribution is missing or zero, which weakens plan trajectory and recommendation quality.',
      href: planAssumptionsHref(plan),
    });
  }

  if (settings.expected_return_baseline == null || settings.expected_return_baseline === '') {
    signals.push({
      id: 'return-assumptions',
      severity: 'review',
      title: 'Expected return assumption needs review',
      detail: 'Expected return is missing, so simulations and long-horizon projections need more context.',
      href: planAssumptionsHref(plan),
    });
  }

  const staleRows = recommendations.filter(row => {
    if (!row || typeof row !== 'object') return false;
    return String(row.source || '').trim().toLowerCase() === 'generator:stale_assumptions';
  });
  if (staleRows.length) {
    const first = staleRows[0] || {};
    const focus = String(first.id || '').trim();
    signals.push({
      id: 'open-stale-assumptions',
      severity: 'review',
      title: 'Open stale-assumption reviews',
      detail: `${staleRows.length} stale-assumption review${staleRows.length === 1 ? '' : 's'} should be resolved before advice is fully trusted.`,
      href: focus ? `#inbox?focus=${encodeURIComponent(focus)}` : '#inbox',
    });
  }

  if (tracking && trackingHasInsufficientHistory(tracking)) {
    signals.push({
      id: 'tracking-history',
      severity: 'review',
      title: 'Tracking history is thin',
      detail: 'Plan confidence will improve after more snapshots and actual contribution history accumulate.',
      href: '#today',
    });
  }

  const thesisRows = recommendations.filter(row => {
    if (!row || typeof row !== 'object') return false;
    return String(row.source || '').trim().toLowerCase() === 'generator:research_thesis_expiration';
  });
  if (thesisRows.length) {
    signals.push({
      id: 'open-research-thesis-reviews',
      severity: 'review',
      title: 'Open research thesis reviews',
      detail: `${thesisRows.length} research thesis review${thesisRows.length === 1 ? '' : 's'} should be resolved before the linked evidence guides plan decisions.`,
      href: researchThesisRecommendationHref(thesisRows[0]),
    });
  }

  const expiredThesisArtifacts = linkedResearchThesisDue(plan, now);
  if (expiredThesisArtifacts.length) {
    const first = expiredThesisArtifacts[0] || {};
    signals.push({
      id: 'linked-research-thesis',
      severity: 'review',
      title: 'Linked research thesis needs review',
      detail: `${expiredThesisArtifacts.length} saved research thesis item${expiredThesisArtifacts.length === 1 ? '' : 's'} linked to this plan should be refreshed before it guides new advice.`,
      href: researchThesisHref(plan, first),
    });
  }

  const unclosedDecisions = acceptedDecisionsWithoutOutcome(plan, now);
  if (unclosedDecisions.length) {
    signals.push({
      id: 'decision-outcomes',
      severity: 'review',
      title: 'Accepted decisions need outcome capture',
      detail: `${unclosedDecisions.length} accepted decision${unclosedDecisions.length === 1 ? '' : 's'} are old enough to need outcome or closure context.`,
      href: planSectionHref(plan, 'decisions'),
    });
  }

  const status = signals.some(signal => signal.severity === 'weak')
    ? 'weak'
    : signals.length
      ? 'needs_review'
      : 'ready';

  return {
    status,
    label: statusLabel(status),
    detail: healthDetail(status, signals),
    signals,
  };
}

export function renderPlanHealth(plan = {}, health = derivePlanHealth(plan)) {
  const signals = Array.isArray(health.signals) ? health.signals : [];
  return html`
    <section class="plan-health ${esc(health.status || 'ready')}" data-plan-section="health">
      <header class="section-head compact">
        <span class="section-eyebrow">Plan health</span>
        <h2 class="section-title">${esc(health.label || statusLabel(health.status))}</h2>
        <p class="section-lede">${esc(health.detail || healthDetail(health.status, signals))}</p>
      </header>
      ${signals.length ? html`
        <ol class="plan-health-list">
          ${raw(signals.slice(0, 6).map(signal => renderSignal(signal)).join(''))}
        </ol>
      ` : html`
        <div class="plan-health-ready">
          <span class="glyph">✓</span>
          <p>Plan context is decision-grade for the current daily loop.</p>
          <a class="link-editorial" href="${planAssumptionsHref(plan)}">Review assumptions</a>
        </div>
      `}
    </section>
  `;
}

function renderSignal(signal) {
  const href = String(signal.href || '').trim();
  return html`
    <li class="plan-health-row ${esc(signal.severity || 'review')}">
      <div>
        <span class="plan-health-severity">${esc(signal.severity === 'weak' ? 'Weak' : 'Needs review')}</span>
        <h3>${esc(signal.title || 'Review plan context')}</h3>
        ${signal.detail ? html`<p>${esc(signal.detail)}</p>` : ''}
      </div>
      ${href ? html`<a class="link-editorial" href="${href}">Open</a>` : ''}
    </li>
  `;
}

function planAssumptionsHref(plan = {}) {
  return planSectionHref(plan, 'assumptions');
}

function planSectionHref(plan = {}, section = '') {
  const id = String(plan.id || '').trim();
  const safeSection = encodeURIComponent(String(section || '').trim());
  return id ? `#plan?id=${encodeURIComponent(id)}&section=${safeSection}` : `#plan?section=${safeSection}`;
}

function trackingHasInsufficientHistory(tracking) {
  const status = String(tracking.status || tracking.tracking_status || '').toLowerCase();
  if (status.includes('insufficient')) return true;
  const snapshotsCount = Number(
    tracking.snapshots_count
    ?? tracking.snapshot_count
    ?? tracking.history_count
    ?? NaN,
  );
  return Number.isFinite(snapshotsCount) && snapshotsCount > 0 && snapshotsCount < 30;
}

function linkedResearchThesisDue(plan, now) {
  const artifacts = Array.isArray(plan?.artifacts) ? plan.artifacts : [];
  return artifacts.filter(artifact => {
    if (!isResearchArtifact(artifact)) return false;
    const review = artifact?.thesis_review && typeof artifact.thesis_review === 'object'
      ? artifact.thesis_review
      : {};
    const expiresAt = parseDate(
      review.expires_at
        ?? artifact.thesis_expires_at
        ?? artifact.expires_at,
    );
    return Boolean(expiresAt && expiresAt <= now);
  });
}

function isResearchArtifact(artifact = {}) {
  const kind = String(artifact.kind || '').toLowerCase();
  const title = String(artifact.title || '').toLowerCase();
  const fileName = String(artifact.file_name || '').toLowerCase();
  return kind.includes('research')
    || fileName.includes('research-dossier')
    || fileName.includes('-research-')
    || title.startsWith('research dossier');
}

function researchThesisHref(plan = {}, artifact = {}) {
  const artifactId = String(artifact.id || artifact.artifact_id || '').trim();
  if (!artifactId) return '#research';
  const planId = String(plan.id || '').trim();
  const planParam = planId ? `&plan=${encodeURIComponent(planId)}` : '';
  return `#research?thesisReview=${encodeURIComponent(artifactId)}${planParam}`;
}

function researchThesisRecommendationHref(row = {}) {
  const payload = row.action_payload && typeof row.action_payload === 'object'
    ? row.action_payload
    : {};
  const suggested = payload.suggested_action && typeof payload.suggested_action === 'object'
    ? payload.suggested_action
    : {};
  const evidence = payload.evidence && typeof payload.evidence === 'object'
    ? payload.evidence
    : {};
  const artifactId = String(suggested.artifact_id || evidence.artifact_id || '').trim();
  const symbols = Array.isArray(suggested.symbols)
    ? suggested.symbols
    : Array.isArray(evidence.symbols)
      ? evidence.symbols
      : [];
  const target = artifactId || String(symbols[0] || '').trim().toUpperCase();
  const focus = String(row.id || '').trim();
  if (!target) return focus ? `#inbox?focus=${encodeURIComponent(focus)}` : '#inbox';
  const planId = String(suggested.plan_id || evidence.plan_id || row.plan_id || '').trim();
  const params = [
    `thesisReview=${encodeURIComponent(target)}`,
    planId ? `plan=${encodeURIComponent(planId)}` : '',
    focus ? `focus=${encodeURIComponent(focus)}` : '',
  ].filter(Boolean).join('&');
  return `#research?${params}`;
}

function acceptedDecisionsWithoutOutcome(plan, now) {
  const decisions = Array.isArray(plan?.decisions) ? plan.decisions : [];
  const cutoffMs = 45 * 24 * 60 * 60 * 1000;
  return decisions.filter(decision => {
    const status = String(decision?.status || '').toLowerCase();
    if (!['accepted', 'approved', 'applied', 'done'].includes(status)) return false;
    if (decisionHasClosure(decision)) return false;
    const createdAt = parseDate(decision.created_at || decision.accepted_at || decision.updated_at);
    return Boolean(createdAt && now.getTime() - createdAt.getTime() >= cutoffMs);
  });
}

function decisionHasClosure(decision = {}) {
  const payload = decision.action_payload && typeof decision.action_payload === 'object'
    ? decision.action_payload
    : {};
  return Boolean(
    decision.outcome_captured
      || decision.closure_artifact_id
      || decision.decision_closure_artifact
      || decision.outcome_artifact_id
      || decision.realized_outcome
      || decision.expected_vs_realized
      || payload.decision_closure
      || payload.realized_outcome
      || payload.expected_vs_realized,
  );
}

function parseDate(value) {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function statusLabel(status) {
  if (status === 'weak') return 'Weak';
  if (status === 'needs_review') return 'Needs review';
  return 'Ready';
}

function healthDetail(status, signals) {
  if (status === 'weak') {
    return 'Core assumptions are missing or weak enough to lower plan confidence.';
  }
  if (status === 'needs_review') {
    return `${signals.length} plan context signal${signals.length === 1 ? '' : 's'} need review before advice is fully trusted.`;
  }
  return 'Plan context is decision-grade for the current daily loop.';
}
