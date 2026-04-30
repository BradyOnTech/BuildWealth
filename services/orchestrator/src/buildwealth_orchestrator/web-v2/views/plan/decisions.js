// Movement III — The decisions.
// Editorial list of plan decisions with an inline append form.

import { html, raw, esc } from '../../lib/dom.js';
import { roman, fmtRelative, fmtUsdSigned } from '../../lib/format.js';

export function renderDecisions(plan, state) {
  const decisions = (plan.decisions || []).slice().reverse();
  const planId = String(plan.id || '').trim();

  return html`
    <section>
      <header class="section-head">
        <span class="section-eyebrow">Movement III</span>
        <h2 class="section-title">The decisions.</h2>
        <p class="section-lede">A trail of what was changed and why — useful when calibration revisits results.</p>
      </header>
      ${decisions.length ? renderList(decisions, planId) : renderEmpty()}
      ${renderAppendArea(state)}
    </section>
  `;
}

function renderList(decisions, planId = '') {
  return html`
    <ol class="decision-list">
      ${decisions.slice(0, 12).map((d, i) => renderRow(d, i + 1, planId))}
    </ol>
  `;
}

function renderRow(decision, index, planId = '') {
  const rawStatus = String(decision.status || 'proposed').toLowerCase();
  const tier = canonicalStatus(rawStatus);
  const created = decision.created_at ? fmtRelative(decision.created_at) : '';
  const dateLabel = decision.created_at
    ? new Date(decision.created_at).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
    : '';

  return html`
    <li class="decision-row">
      <span class="decision-numeral">${roman(index)}.</span>
      <div>
        <div class="decision-tag">
          ${dateLabel ? html`<span>${dateLabel.toUpperCase()}</span>` : ''}
          <span class="status ${tier}">
            <span class="dot"></span>${rawStatus}
          </span>
          ${created ? html`<span class="marginalia" style="font-family:var(--serif);font-style:italic;text-transform:none;letter-spacing:0;">${created}</span>` : ''}
        </div>
        <p class="decision-summary">${esc(decision.summary || '')}</p>
        ${decision.rationale ? html`<p class="decision-rationale">${esc(decision.rationale)}</p>` : ''}
        ${raw(renderDecisionMeta(decision, planId))}
      </div>
    </li>
  `;
}

// Map free-form status strings to one of three editorial buckets so the
// dot colour stays consistent regardless of the verb the writer reached for.
function canonicalStatus(s) {
  if (s === 'accepted' || s === 'approved' || s === 'applied' || s === 'done')   return 'accepted';
  if (s === 'rejected' || s === 'declined' || s === 'cancelled' || s === 'abandoned') return 'rejected';
  return 'proposed';
}

function renderDecisionMeta(decision = {}, planId = '') {
  const meta = decisionMeta(decision, planId);
  const links = decisionLinks(meta);
  const details = decisionDetails(meta);
  if (!links.length && !details.length) return '';

  return html`
    <div class="decision-meta">
      ${links.length ? html`
        <div class="decision-meta-links">
          ${raw(links.map(link => html`<a class="link-editorial" href="${link.href}">${link.label}</a>`).join(''))}
        </div>
      ` : ''}
      ${details.length ? html`
        <dl class="decision-meta-list">
          ${raw(details.map(item => html`
            <div>
              <dt>${item.label}</dt>
              <dd>${item.value}</dd>
            </div>
          `).join(''))}
        </dl>
      ` : ''}
    </div>
  `;
}

function decisionMeta(decision = {}, planId = '') {
  const payload = objectValue(decision.action_payload);
  const closure = firstObject(decision.decision_closure, payload.decision_closure);
  const packet = firstObject(decision.decision_packet, payload.decision_packet);
  const closureArtifact = firstObject(decision.decision_closure_artifact, payload.decision_closure_artifact);
  const expectedOutcome = firstObject(
    decision.expected_outcome,
    payload.expected_outcome,
    closure.expected_outcome,
  );
  const scenarioPreview = firstObject(
    decision.scenario_diff_preview,
    payload.scenario_diff_preview,
    closure.scenario_diff_preview,
  );

  return {
    status: String(decision.status || '').toLowerCase(),
    planId: clean(decision.plan_id || payload.plan_id || packet.plan_id || closureArtifact.plan_id || planId),
    recommendationId: clean(
      decision.recommendation_id
        || decision.source_recommendation_id
        || payload.recommendation_id
        || payload.source_recommendation_id
        || objectValue(payload.recommendation).id
        || closure.recommendation_id,
    ),
    decisionPacketArtifactId: clean(
      decision.decision_packet_artifact_id
        || decision.artifact_id
        || packet.artifact_id
        || packet.id,
    ),
    closureArtifactId: clean(
      decision.closure_artifact_id
        || decision.outcome_artifact_id
        || closureArtifact.artifact_id
        || closureArtifact.id,
    ),
    expectedOutcome,
    scenarioPreview,
    outcomeCaptured: decisionHasOutcome(decision, payload, closure, closureArtifact),
  };
}

function decisionLinks(meta) {
  const links = [];
  if (meta.recommendationId) {
    links.push({
      label: 'Open in Inbox',
      href: `#inbox?focus=${encodeURIComponent(meta.recommendationId)}`,
    });
  }
  if (meta.decisionPacketArtifactId) {
    links.push({
      label: 'Decision packet',
      href: artifactHref(meta.planId, meta.decisionPacketArtifactId),
    });
  }
  if (meta.closureArtifactId) {
    links.push({
      label: 'Closure summary',
      href: artifactHref(meta.planId, meta.closureArtifactId),
    });
  }
  return links;
}

function decisionDetails(meta) {
  const details = [];
  const expected = expectedOutcomeText(meta.expectedOutcome);
  const scenario = scenarioPreviewText(meta.scenarioPreview);
  if (expected) details.push({ label: 'Expected outcome', value: expected });
  if (scenario) details.push({ label: 'Scenario preview', value: scenario });
  if (meta.outcomeCaptured) {
    details.push({ label: 'Outcome', value: 'Outcome captured' });
  } else if (isAcceptedStatus(meta.status)) {
    details.push({ label: 'Outcome', value: 'Outcome not captured yet' });
  }
  return details;
}

function expectedOutcomeText(outcome = {}) {
  if (!outcome || !Object.keys(outcome).length) return '';
  const parts = [];
  if (Number.isFinite(Number(outcome.expected_delta_future_value_usd))) {
    parts.push(`Future value ${fmtUsdSigned(Number(outcome.expected_delta_future_value_usd))}`);
  }
  if (Number.isFinite(Number(outcome.expected_delta_real_value_usd))) {
    parts.push(`Real value ${fmtUsdSigned(Number(outcome.expected_delta_real_value_usd))}`);
  }
  const quality = clean(
    outcome.expected_delta_context_quality
      || outcome.expected_delta_assumption_quality
      || outcome.expected_delta_projection_quality
      || outcome.expected_delta_tracking_quality
      || outcome.expected_delta_decision_trace_quality,
  );
  if (quality) parts.push(quality.replace(/_/g, ' '));
  return parts.join(' · ');
}

function scenarioPreviewText(preview = {}) {
  if (!preview || !Object.keys(preview).length) return '';
  return clean(
    preview.summary
      || preview.detail
      || preview.description
      || preview.status,
  );
}

function decisionHasOutcome(decision = {}, payload = {}, closure = {}, closureArtifact = {}) {
  return Boolean(
    decision.outcome_captured
      || decision.closure_artifact_id
      || decision.outcome_artifact_id
      || decision.realized_outcome
      || decision.expected_vs_realized
      || payload.realized_outcome
      || payload.expected_vs_realized
      || closure.realized_outcome
      || closure.expected_vs_realized
      || closureArtifact.artifact_id
      || closureArtifact.id,
  );
}

function artifactHref(planId, artifactId) {
  const params = new URLSearchParams();
  if (planId) params.set('id', planId);
  params.set('section', 'artifacts');
  if (artifactId) params.set('artifact', artifactId);
  return `#plan?${params.toString()}`;
}

function isAcceptedStatus(status) {
  return ['accepted', 'approved', 'applied', 'done'].includes(String(status || '').toLowerCase());
}

function objectValue(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function firstObject(...values) {
  for (const value of values) {
    const candidate = objectValue(value);
    if (Object.keys(candidate).length) return candidate;
  }
  return {};
}

function clean(value) {
  return String(value ?? '').trim();
}

function renderEmpty() {
  return html`
    <div class="empty-block">
      <span class="glyph">¶</span>
      <p>No decisions logged yet.</p>
    </div>
  `;
}

function renderAppendArea(state) {
  if (!state.appendOpen) {
    return html`
      <div class="entry-actions" style="margin-top: var(--s-4);">
        <button class="action-link" data-decision-action="open-append">
          Append a decision <span class="arrow">›</span>
        </button>
      </div>
    `;
  }

  return html`
    <div class="append-form" data-form="append-decision">
      <p class="inline-form-title">Log a decision.</p>
      <div class="inline-form-row">
        <label class="inline-label" for="decision-summary">Summary</label>
        <input id="decision-summary" name="summary" type="text" placeholder="What changed, briefly." />
      </div>
      <div class="inline-form-row">
        <label class="inline-label" for="decision-rationale">Rationale (optional)</label>
        <textarea id="decision-rationale" name="rationale" placeholder="Why now? What were you weighing?"></textarea>
      </div>
      <div class="inline-form-row">
        <label class="inline-label" for="decision-status">Status</label>
        <select id="decision-status" name="status">
          <option value="accepted">accepted</option>
          <option value="proposed" selected>proposed</option>
          <option value="rejected">rejected</option>
        </select>
      </div>
      ${state.appendError ? html`<p class="inline-warning">${esc(state.appendError)}</p>` : ''}
      <div class="append-form-actions">
        <button class="btn btn-primary" data-decision-action="submit-append" ${state.appendBusy ? 'disabled' : ''}>
          ${state.appendBusy ? 'Saving…' : 'Save'}
        </button>
        <button class="btn btn-ghost" data-decision-action="cancel-append" ${state.appendBusy ? 'disabled' : ''}>Cancel</button>
      </div>
    </div>
  `;
}
