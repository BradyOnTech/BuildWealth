// Inbox entries — render the list and each entry header.
// Inline action forms are rendered by ./forms.js.

import { html, raw, esc, stripHtml } from '../../lib/dom.js';
import { roman, fmtRelative } from '../../lib/format.js';
import { renderInlineForm } from './forms.js';

const STATUS_LABELS = {
  proposed: 'proposed',
  applied:  'applied',
  rejected: 'declined',
  archived: 'archived',
};

export function renderEntries(items, ctx) {
  if (!items.length) {
    return html`
      <div class="empty-block">
        <span class="glyph">¶</span>
        <p>${ctx.emptyMessage || 'No suggestions in this lane.'}</p>
      </div>
    `;
  }
  return html`
    <ol class="entry-list">
      ${raw(items.map((it, i) => renderEntry(it, i + 1, ctx)).join(''))}
    </ol>
  `;
}

function renderEntry(item, index, ctx) {
  const status = (item.status || 'proposed').toLowerCase();
  const priority = (item.priority || 'medium').toLowerCase();
  const source = humanSource(item.source);
  const recoType = humanText(item.recommendation_type);
  const planLabel = ctx.planLookup.get(item.plan_id) || (item.plan_id ? 'plan' : '');
  const score = item.score?.total != null ? Math.round(item.score.total) : null;
  const reasons = (item.score?.reasons || []).slice(0, 2);
  const updated = item.updated_at ? fmtRelative(item.updated_at) : '';
  const expanded = ctx.expanded && ctx.expanded.id === item.id ? ctx.expanded : null;

  return html`
    <li class="entry" data-id="${item.id}">
      <span class="entry-numeral">${roman(index)}.</span>
      <div class="entry-body">
        ${raw(renderTagRow({ status, priority, source, recoType, planLabel, score, updated }))}
        <h3 class="entry-title">${stripHtml(item.title)}</h3>
        ${raw(detailMarkup(item.detail))}
        ${raw(renderQualitySummary(item.action_payload?.quality))}
        ${raw(renderInvestmentRoutePanel(item))}
        ${raw(renderSavedSimulationRoutePanel(item))}
        ${reasons.length ? raw(`
          <p class="marginalia">
            <span class="glyph">›</span> ${reasons.map(esc).join(' · ')}
          </p>
        `) : ''}
        ${raw(renderActions(item, status, expanded))}
        ${expanded ? raw(renderInlineForm(item, expanded, ctx)) : ''}
      </div>
    </li>
  `;
}

function renderTagRow({ status, priority, source, recoType, planLabel, score, updated }) {
  const parts = [];
  parts.push(html`
    <span class="status-pill ${status}">
      <span class="dot"></span>${STATUS_LABELS[status] || status}
    </span>
  `);
  if (status === 'proposed') {
    parts.push(html`
      <span class="entry-tag">
        <span class="priority ${priority}"></span>${priority} priority
      </span>
    `);
  }
  if (source) parts.push(html`<span class="entry-tag">${source}</span>`);
  if (recoType && recoType !== 'general') parts.push(html`<span class="entry-tag">${recoType}</span>`);
  if (planLabel) parts.push(html`<span class="entry-tag">${planLabel}</span>`);
  if (score != null) parts.push(html`<span class="entry-tag">score ${score}</span>`);
  if (updated) parts.push(html`<span class="entry-tag">${updated}</span>`);
  return html`<div class="entry-tag" style="display:flex;flex-wrap:wrap;gap:var(--s-4);">${raw(parts.join(''))}</div>`;
}

function renderActions(item, status, expanded) {
  const expandedMode = expanded?.mode || null;
  if (status === 'proposed') {
    const semantics = actionSemantics(item);
    const defaultCopilotHref = semantics.intent
      ? `#copilot?focus=${encodeURIComponent(item.id)}&intent=${encodeURIComponent(semantics.intent)}`
      : `#copilot?focus=${encodeURIComponent(item.id)}`;
    const primaryHref = semantics.href || defaultCopilotHref;
    return html`
      <div class="entry-actions">
        ${semantics.primaryAction === 'apply' ? html`
          <button class="action-link" data-action="apply" data-id="${item.id}"
            aria-expanded="${expandedMode === 'apply'}">
            ${semantics.primaryLabel} <span class="arrow">›</span>
          </button>
        ` : html`
          <a class="action-link" href="${primaryHref}">
            ${semantics.primaryLabel} <span class="arrow">→</span>
          </a>
        `}
        <button class="action-link danger" data-action="decline" data-id="${item.id}"
          aria-expanded="${expandedMode === 'decline'}">
          Decline <span class="arrow">›</span>
        </button>
        <a class="action-link muted" href="#copilot?focus=${encodeURIComponent(item.id)}">
          Discuss in Copilot <span class="arrow">→</span>
        </a>
      </div>
    `;
  }
  if (status === 'applied' || status === 'rejected') {
    return html`
      <div class="entry-actions">
        <button class="action-link" data-action="outcome" data-id="${item.id}"
          aria-expanded="${expandedMode === 'outcome'}">
          Log outcome <span class="arrow">›</span>
        </button>
        <button class="action-link muted" data-action="archive" data-id="${item.id}">
          Archive <span class="arrow">›</span>
        </button>
      </div>
    `;
  }
  return '';
}

function actionSemantics(item) {
  const quality = item?.action_payload?.quality;
  const investment = investmentContext(item);
  const savedSimulation = savedSimulationContext(item);
  if (savedSimulation) {
    return {
      primaryAction: 'route',
      primaryLabel: 'Open simulation',
      href: savedSimulation.href,
      intent: 'saved-simulation',
    };
  }
  if (investment) {
    const suggestedKind = String(investment.suggestedAction?.kind || '').toLowerCase();
    if (suggestedKind === 'refresh_research_evidence' || suggestedKind === 'research_more' || suggestedKind === 'create_dossier') {
      return {
        primaryAction: 'route',
        primaryLabel: suggestedKind === 'create_dossier' ? 'Create dossier' : 'Open research',
        href: investment.researchHref,
        intent: 'investment-fit',
      };
    }
    if (suggestedKind === 'review_research_thesis') {
      return {
        primaryAction: 'route',
        primaryLabel: 'Review thesis',
        href: investment.thesisReviewHref || investment.dossierHref || investment.researchHref,
        intent: 'investment-fit',
      };
    }
    if (suggestedKind === 'compare_alternatives') {
      return {
        primaryAction: 'route',
        primaryLabel: 'Compare candidates',
        href: investment.compareHref,
        intent: 'investment-fit',
      };
    }
    if (suggestedKind === 'update_profile') {
      return {
        primaryAction: 'copilot',
        primaryLabel: 'Complete context',
        intent: 'complete-context',
      };
    }
    return {
      primaryAction: 'route',
      primaryLabel: 'Review fit',
      href: investment.fitHref,
      intent: 'investment-fit',
    };
  }
  const actionability = quality && typeof quality === 'object'
    ? String(quality.actionability || '').trim().toLowerCase()
    : '';
  if (actionability === 'context_gathering') {
    return {
      primaryAction: 'copilot',
      primaryLabel: 'Complete context',
      intent: 'complete-context',
    };
  }
  if (actionability === 'review_only') {
    return {
      primaryAction: 'copilot',
      primaryLabel: 'Review decision',
      intent: 'review-decision',
    };
  }
  if (actionability === 'previewable') {
    return {
      primaryAction: 'apply',
      primaryLabel: 'Preview & apply',
      intent: '',
    };
  }
  return {
    primaryAction: 'apply',
    primaryLabel: 'Apply',
    intent: '',
  };
}

function renderInvestmentRoutePanel(item) {
  const investment = investmentContext(item);
  if (!investment) return '';
  const evidence = investment.evidence;
  const meta = [
    investment.symbol ? `symbol ${investment.symbol}` : '',
    evidence.freshness_status ? `${humanText(evidence.freshness_status)} evidence` : '',
    evidence.provider ? `via ${evidence.provider}` : '',
    evidence.fit_status ? `${humanText(evidence.fit_status)} fit` : '',
  ].filter(Boolean);
  return html`
    <div class="investment-route-panel">
      <div>
        <span class="investment-route-kicker">Investment-fit route</span>
        <p>${meta.join(' · ') || 'Research-backed review'}</p>
      </div>
      <div class="investment-route-actions">
        <a class="action-link" href="${investment.fitHref}">Review fit <span class="arrow">→</span></a>
        ${investment.thesisReviewHref ? html`<a class="action-link muted" href="${investment.thesisReviewHref}">Thesis <span class="arrow">→</span></a>` : ''}
        ${investment.dossierHref ? html`<a class="action-link muted" href="${investment.dossierHref}">Dossier <span class="arrow">→</span></a>` : ''}
        <a class="action-link muted" href="${investment.researchHref}">Research <span class="arrow">→</span></a>
        <a class="action-link muted" href="${investment.compareHref}">Compare <span class="arrow">→</span></a>
        <a class="action-link muted" href="${investment.copilotHref}">Copilot <span class="arrow">→</span></a>
      </div>
    </div>
  `;
}

function renderSavedSimulationRoutePanel(item) {
  const savedSimulation = savedSimulationContext(item);
  if (!savedSimulation) return '';
  const meta = [
    savedSimulation.title,
    savedSimulation.source ? humanText(savedSimulation.source) : '',
    savedSimulation.planId ? 'plan linked' : '',
  ].filter(Boolean);
  return html`
    <div class="investment-route-panel">
      <div>
        <span class="investment-route-kicker">Saved Simulation route</span>
        <p>${meta.join(' · ') || 'Saved experiment ready for review'}</p>
      </div>
      <div class="investment-route-actions">
        <a class="action-link" href="${savedSimulation.href}">Open simulation <span class="arrow">→</span></a>
        <a class="action-link muted" href="${savedSimulation.copilotHref}">Discuss in Copilot <span class="arrow">→</span></a>
      </div>
    </div>
  `;
}

function investmentContext(item) {
  const payload = item?.action_payload;
  if (!payload || typeof payload !== 'object') return null;
  const generator = payload.generator && typeof payload.generator === 'object' ? payload.generator : {};
  const source = String(item?.source || '').toLowerCase();
  const isResearchRecommendation = source === 'generator:watchlist_research'
    || source === 'generator:research_thesis_expiration'
    || generator.signal_type === 'watchlist_research'
    || generator.signal_type === 'research_thesis_expiration';
  const isCopilotInvestmentDraft = source === 'copilot:investment_fit'
    || generator.signal_type === 'investment_fit_discussion';
  if (!isResearchRecommendation && !isCopilotInvestmentDraft) return null;
  const evidence = payload.evidence && typeof payload.evidence === 'object' ? payload.evidence : {};
  const suggestedAction = payload.suggested_action && typeof payload.suggested_action === 'object'
    ? payload.suggested_action
    : {};
  const symbolList = Array.isArray(suggestedAction.symbols)
    ? suggestedAction.symbols
    : (Array.isArray(evidence.symbols) ? evidence.symbols : []);
  const symbol = String(suggestedAction.symbol || evidence.symbol || symbolList[0] || '').trim().toUpperCase();
  const encodedSymbol = encodeURIComponent(symbol);
  const encodedId = encodeURIComponent(item.id || '');
  const packetId = String(evidence.research_evidence_packet_id || evidence.packet_id || '').trim();
  const packetQuery = packetId ? `&packet=${encodeURIComponent(packetId)}` : '';
  const artifactId = String(suggestedAction.artifact_id || evidence.artifact_id || '').trim();
  const planId = String(suggestedAction.plan_id || evidence.plan_id || item.plan_id || '').trim();
  const dossierHref = artifactId && planId
    ? `#research?dossier=${encodeURIComponent(artifactId)}&plan=${encodeURIComponent(planId)}`
    : '';
  const thesisTarget = artifactId || symbol;
  const thesisPlanQuery = planId ? `&plan=${encodeURIComponent(planId)}` : '';
  const thesisReviewHref = thesisTarget
    ? `#research?thesisReview=${encodeURIComponent(thesisTarget)}${thesisPlanQuery}&focus=${encodedId}`
    : '';
  const fitHref = symbol ? `#portfolio?fit=${encodedSymbol}&focus=${encodedId}` : `#portfolio?focus=${encodedId}`;
  return {
    symbol,
    evidence,
    suggestedAction,
    fitHref,
    thesisReviewHref,
    dossierHref,
    researchHref: symbol ? `#research?symbol=${encodedSymbol}${packetQuery}` : '#research',
    compareHref: symbol ? `#research?compare=${encodedSymbol}${packetQuery}` : '#research',
    copilotHref: `#copilot?focus=${encodedId}&intent=investment-fit`,
  };
}

function savedSimulationContext(item) {
  const payload = item?.action_payload;
  if (!payload || typeof payload !== 'object') return null;
  const saved = payload.saved_simulation && typeof payload.saved_simulation === 'object'
    ? payload.saved_simulation
    : {};
  const simulation = payload.simulation && typeof payload.simulation === 'object'
    ? payload.simulation
    : {};
  const closure = payload.decision_closure && typeof payload.decision_closure === 'object'
    ? payload.decision_closure
    : {};
  const savedSimulationId = String(
    payload.saved_simulation_id
      || saved.id
      || simulation.saved_simulation_id
      || simulation.id
      || closure.saved_simulation_id
      || '',
  ).trim();
  if (!savedSimulationId) return null;
  const planId = String(
    payload.plan_id
      || saved.plan_id
      || simulation.plan_id
      || closure.plan_id
      || item?.plan_id
      || '',
  ).trim();
  const params = new URLSearchParams();
  if (planId) params.set('id', planId);
  params.set('section', 'scenarios');
  params.set('saved', savedSimulationId);
  const copilotParams = new URLSearchParams();
  if (item?.id) copilotParams.set('focus', item.id);
  copilotParams.set('intent', 'saved-simulation');
  if (planId) copilotParams.set('plan', planId);
  copilotParams.set('saved', savedSimulationId);
  return {
    id: savedSimulationId,
    planId,
    title: String(payload.saved_simulation_title || saved.title || simulation.title || '').trim(),
    source: String(payload.source || saved.source || simulation.source || '').trim(),
    href: `#plan?${params.toString()}`,
    copilotHref: `#copilot?${copilotParams.toString()}`,
  };
}

function renderQualitySummary(quality) {
  if (!quality || typeof quality !== 'object') return '';
  const confidence = humanText(quality.confidence_level);
  const freshness = humanText(quality.freshness_status);
  const actionability = humanText(quality.actionability);
  const reversibility = humanText(quality.reversibility);
  const impact = quality.impact && typeof quality.impact === 'object' ? humanText(quality.impact.level) : '';
  const decisionGrade = quality.decision_grade === true ? 'decision grade' : '';
  const blockers = Array.isArray(quality.blocking_context)
    ? quality.blocking_context.map(humanText).filter(Boolean)
    : [];
  const blocking = blockers.length
    ? `${blockers.length} blocker${blockers.length === 1 ? '' : 's'}: ${blockers.slice(0, 3).join(', ')}`
    : '';
  const parts = [
    confidence ? `${confidence} confidence` : '',
    freshness ? `${freshness} evidence` : '',
    actionability,
    reversibility ? `${reversibility} reversibility` : '',
    impact ? `${impact} impact` : '',
    decisionGrade,
    blocking,
  ].filter(Boolean);
  if (!parts.length) return '';
  return html`
    <p class="marginalia quality-line">
      <span class="glyph">›</span> ${parts.map(esc).join(' · ')}
    </p>
  `;
}

function humanText(value) {
  if (!value) return '';
  return String(value).replace(/[_.]/g, ' ');
}

function detailMarkup(raw) {
  const text = stripHtml(raw);
  return text ? `<p class="entry-rationale">${esc(text)}</p>` : '';
}

// Sources arrive as "generator:plan_tracking" / "manual" / "today_dashboard_heuristic".
// Strip namespace prefix and prepend "from " so the tag reads naturally.
function humanSource(value) {
  if (!value) return '';
  const stripped = String(value).split(':').pop().replace(/_/g, ' ').trim();
  if (!stripped || stripped === 'manual') return stripped;
  return `from ${stripped}`;
}
