// Movement IIA — Plan evidence.
// Typed artifact center for durable research, decision, closure, and scenario memory.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtDateLong } from '../../lib/format.js';

const TYPE_LABELS = {
  research_dossier: 'Research dossier',
  research_bridge: 'Research bridge',
  decision_packet: 'Decision packet',
  thesis_revision: 'Thesis revision',
  closure_summary: 'Outcome/closure',
  scenario_report: 'Scenario report',
  general: 'General artifact',
};

export function classifyPlanArtifact(artifact = {}) {
  const kind = clean(artifact.kind).toLowerCase();
  const title = clean(artifact.title).toLowerCase();
  const fileName = clean(artifact.file_name).toLowerCase();

  if (kind === 'research_dossier' || fileName.includes('research-dossier') || title.startsWith('research dossier')) {
    return { kind: 'research_dossier', label: TYPE_LABELS.research_dossier };
  }
  if (kind === 'research_bridge' || title.includes('research bridge') || fileName.includes('research-bridge')) {
    return { kind: 'research_bridge', label: TYPE_LABELS.research_bridge };
  }
  if (kind === 'decision_packet' || title.includes('decision packet') || fileName.includes('decision-packet')) {
    return { kind: 'decision_packet', label: TYPE_LABELS.decision_packet };
  }
  if (kind === 'thesis_revision' || title.includes('thesis revision') || fileName.includes('thesis-revision')) {
    return { kind: 'thesis_revision', label: TYPE_LABELS.thesis_revision };
  }
  if (
    kind === 'closure_summary'
    || kind === 'recommendation_closure'
    || title.includes('closure')
    || title.includes('outcome')
    || fileName.includes('closure')
    || fileName.includes('outcome')
  ) {
    return { kind: 'closure_summary', label: TYPE_LABELS.closure_summary };
  }
  if (kind === 'scenario_report' || title.includes('scenario') || fileName.includes('scenario')) {
    return { kind: 'scenario_report', label: TYPE_LABELS.scenario_report };
  }
  return { kind: 'general', label: TYPE_LABELS.general };
}

export function renderArtifacts(plan = {}, state = {}) {
  const artifacts = Array.isArray(plan.artifacts) ? plan.artifacts : [];
  const planId = clean(plan.id);

  return html`
    <section class="plan-artifacts" data-plan-section="artifacts">
      <header class="section-head compact">
        <span class="section-eyebrow">Plan evidence</span>
        <h2 class="section-title">Artifacts and evidence.</h2>
        <p class="section-lede">Saved research, decision packets, closure summaries, and scenario reports that explain how this plan learned.</p>
      </header>
      ${raw(renderFocusedArtifact(planId, state))}
      ${artifacts.length ? html`
        <ol class="artifact-list">
          ${raw(artifacts.slice(0, 12).map(artifact => renderArtifactCard(artifact, planId)).join(''))}
        </ol>
      ` : html`
        <div class="empty-block">
          <span class="glyph">§</span>
          <p>No saved plan artifacts yet.</p>
        </div>
      `}
    </section>
  `;
}

function renderFocusedArtifact(planId = '', state = {}) {
  const artifact = objectValue(state.focusedArtifact);
  const id = clean(state.focusedArtifactId || artifact.id);
  if (state.busy && id) {
    return html`
      <article class="scenario-result artifact-detail-panel">
        <span class="section-eyebrow">Artifact detail</span>
        <div class="skeleton" style="height: 180px;">.</div>
      </article>
    `;
  }
  if (state.error && id) {
    return html`
      <article class="scenario-result artifact-detail-panel">
        <span class="section-eyebrow">Artifact detail</span>
        <p class="error-banner">${esc(state.error)}</p>
        <a class="link-editorial" href="#plan?id=${encodeURIComponent(planId)}&amp;section=artifacts">Back to artifacts</a>
      </article>
    `;
  }
  if (!Object.keys(artifact).length) return '';

  const classified = classifyPlanArtifact(artifact);
  const title = clean(artifact.title || artifact.file_name || artifact.id || classified.label);
  const created = fmtDateLong(artifact.created_at);
  const content = clean(artifact.content || artifact.content_preview || artifact.summary || artifact.detail);
  const citations = packetCitations(artifact);
  const actions = focusedArtifactActions(planId, artifact, classified.kind);

  return html`
    <article class="scenario-result artifact-detail-panel">
      <header class="section-head compact">
        <span class="section-eyebrow">Artifact detail</span>
        <h3 class="section-title">${esc(title)}</h3>
        <p class="section-lede">${esc(classified.label)}${created ? ` · ${created}` : ''}${artifact.file_name ? ` · ${artifact.file_name}` : ''}</p>
      </header>

      ${citations.length ? html`
        <div class="artifact-citations" aria-label="Packet citations">
          ${raw(citations.slice(0, 8).map(citation => html`<code>${citation}</code>`).join(''))}
        </div>
      ` : ''}

      ${content ? html`<pre class="artifact-detail-content">${content}</pre>` : html`<p class="marginalia">No artifact content was returned.</p>`}

      <div class="scenario-handoff">
        <a class="link-editorial" href="#plan?id=${encodeURIComponent(planId)}&amp;section=artifacts">Back to artifacts</a>
        ${raw(actions.map(link => html`<a class="link-editorial" href="${link.href}">${link.label}</a>`).join(''))}
      </div>
    </article>
  `;
}

function renderArtifactCard(artifact = {}, planId = '') {
  const classified = classifyPlanArtifact(artifact);
  const title = clean(artifact.title || artifact.file_name || artifact.id || classified.label);
  const created = fmtDateLong(artifact.created_at);
  const links = artifactLinks(artifact, classified.kind, planId);
  const citations = packetCitations(artifact);

  return html`
    <li class="artifact-card ${esc(classified.kind)}">
      <div class="artifact-card-main">
        <span class="artifact-type">${classified.label}</span>
        <h3>${title}</h3>
        ${created ? html`<p class="artifact-meta">${created}</p>` : ''}
        ${artifactSummary(artifact) ? html`<p class="artifact-summary">${artifactSummary(artifact)}</p>` : ''}
        ${citations.length ? html`
          <div class="artifact-citations" aria-label="Packet citations">
            ${raw(citations.slice(0, 4).map(citation => html`<code>${citation}</code>`).join(''))}
          </div>
        ` : ''}
      </div>
      ${links.length ? html`
        <div class="artifact-actions">
          ${raw(links.map(link => html`<a class="link-editorial" href="${link.href}">${link.label}</a>`).join(''))}
        </div>
      ` : ''}
    </li>
  `;
}

function artifactLinks(artifact = {}, kind = 'general', planId = '') {
  const id = clean(artifact.id || artifact.artifact_id);
  const recommendationId = clean(artifact.recommendation_id || artifact.source_recommendation_id);
  const encodedPlan = planId ? encodeURIComponent(planId) : '';
  const encodedId = id ? encodeURIComponent(id) : '';
  const links = [];

  if (kind === 'research_dossier' && encodedId) {
    links.push({ label: 'Open dossier', href: `#research?dossier=${encodedId}${encodedPlan ? `&plan=${encodedPlan}` : ''}` });
    links.push({ label: 'Review thesis', href: `#research?thesisReview=${encodedId}${encodedPlan ? `&plan=${encodedPlan}` : ''}` });
    return links;
  }

  if (kind === 'research_bridge' && encodedId) {
    links.push({ label: 'Open artifact', href: planArtifactHref(planId, id) });
    const firstSymbol = firstSymbolForArtifact(artifact);
    if (firstSymbol) links.push({ label: 'Research symbol', href: `#research?packet=${encodeURIComponent(firstSymbol)}` });
    return links;
  }

  if (kind === 'decision_packet') {
    if (recommendationId) links.push({ label: 'Open recommendation', href: `#inbox?focus=${encodeURIComponent(recommendationId)}` });
    if (encodedPlan) links.push({ label: 'Decision ledger', href: `#plan?id=${encodedPlan}&section=decisions` });
    return links;
  }

  if (kind === 'thesis_revision') {
    const thesisTarget = clean(
      artifact.target_artifact_id
        || artifact.dossier_artifact_id
        || artifact.revised_artifact_id
        || firstSymbolForArtifact(artifact),
    );
    if (thesisTarget) {
      links.push({
        label: 'Review thesis',
        href: `#research?thesisReview=${encodeURIComponent(thesisTarget)}${encodedPlan ? `&plan=${encodedPlan}` : ''}`,
      });
    }
    if (id) links.push({ label: 'Open artifact', href: planArtifactHref(planId, id) });
    return links;
  }

  if (kind === 'closure_summary') {
    if (recommendationId) links.push({ label: 'Open outcome', href: `#inbox?focus=${encodeURIComponent(recommendationId)}` });
    if (encodedPlan) links.push({ label: 'Decision ledger', href: `#plan?id=${encodedPlan}&section=decisions` });
    return links;
  }

  if (kind === 'scenario_report') {
    if (encodedPlan) links.push({ label: 'Run scenario', href: `#plan?id=${encodedPlan}&section=scenarios` });
    if (id) links.push({ label: 'Open artifact', href: planArtifactHref(planId, id) });
    return links;
  }

  if (id) links.push({ label: 'Open artifact', href: planArtifactHref(planId, id) });
  return links;
}

function focusedArtifactActions(planId = '', artifact = {}, kind = 'general') {
  const id = clean(artifact.id || artifact.artifact_id);
  const recommendationId = clean(artifact.recommendation_id || artifact.source_recommendation_id);
  const encodedPlan = planId ? encodeURIComponent(planId) : '';
  const encodedId = id ? encodeURIComponent(id) : '';
  const links = [];
  if (kind === 'research_dossier' && encodedId) {
    links.push({ label: 'Open dossier', href: `#research?dossier=${encodedId}${encodedPlan ? `&plan=${encodedPlan}` : ''}` });
    links.push({ label: 'Review thesis', href: `#research?thesisReview=${encodedId}${encodedPlan ? `&plan=${encodedPlan}` : ''}` });
  }
  const firstSymbol = firstSymbolForArtifact(artifact) || firstSymbolForCitations(packetCitations(artifact));
  if (firstSymbol) links.push({ label: 'Research symbol', href: `#research?packet=${encodeURIComponent(firstSymbol)}` });
  if (recommendationId) links.push({ label: 'Open recommendation', href: `#inbox?focus=${encodeURIComponent(recommendationId)}` });
  if (encodedPlan) links.push({ label: 'Decision ledger', href: `#plan?id=${encodedPlan}&section=decisions` });
  return links;
}

function planArtifactHref(planId, artifactId) {
  const params = new URLSearchParams();
  if (planId) params.set('id', planId);
  params.set('section', 'artifacts');
  if (artifactId) params.set('artifact', artifactId);
  return `#plan?${params.toString()}`;
}

function artifactSummary(artifact = {}) {
  return clean(
    artifact.summary
      || artifact.description
      || artifact.detail
      || artifact.content_preview,
  );
}

function packetCitations(artifact = {}) {
  const direct = Array.isArray(artifact.packet_citations) ? artifact.packet_citations : [];
  const nested = artifact.evidence && typeof artifact.evidence === 'object' && Array.isArray(artifact.evidence.packet_citations)
    ? artifact.evidence.packet_citations
    : [];
  const text = [
    artifact.content_preview,
    artifact.content,
    artifact.summary,
    artifact.detail,
  ].map(clean).join(' ');
  const embedded = text.match(/research-evidence:[A-Za-z0-9._:-]+/g) || [];
  return [...new Set([...direct, ...nested, ...embedded].map(clean).filter(Boolean))];
}

function firstSymbolForArtifact(artifact = {}) {
  const symbols = Array.isArray(artifact.symbols) ? artifact.symbols : [];
  return clean(symbols[0]).toUpperCase();
}

function firstSymbolForCitations(citations = []) {
  for (const citation of citations) {
    const match = clean(citation).match(/^research-evidence:[^:]+:([^:]+):/);
    if (match) return match[1].toUpperCase();
  }
  return '';
}

function objectValue(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function clean(value) {
  return String(value ?? '').trim();
}
