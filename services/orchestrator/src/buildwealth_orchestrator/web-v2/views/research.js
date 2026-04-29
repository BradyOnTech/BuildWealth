// RESEARCH — packet-native evidence inspection for investment-fit workflows.

import { api } from '../lib/api.js';
import { html, raw, $, setView, delegate } from '../lib/dom.js';
import { fmtPctSigned, fmtTimeShort, fmtUsd } from '../lib/format.js';
import { renderMarkdown } from './copilot/markdown.js';

export const meta = {
  id: 'research',
  label: 'Research',
  numeral: 'V',
  group: 'studio',
};

export function template() {
  return html`
    <section class="page" id="research-page">
      ${raw(renderResearchEmpty())}
    </section>
  `;
}

export async function init(params = {}) {
  const root = $('#research-page');
  if (!root) return;
  const compareSymbols = normalizeCompareSymbols(params.compare || '');
  const symbol = String(params.symbol || compareSymbols[0] || '').trim().toUpperCase();
  const period = String(params.period || '6mo').trim() || '6mo';
  const interval = String(params.interval || '1d').trim() || '1d';
  const planId = String(params.plan || params.plan_id || '').trim();

  if (params.thesisReview != null || params.thesis_review != null) {
    await loadThesisReviewSurface(root, {
      reviewTarget: String(params.thesisReview || params.thesis_review || '').trim(),
      focusId: String(params.focus || '').trim(),
      planId,
      artifactParam: String(params.artifact || '').trim(),
      period,
      interval,
    });
    return;
  }

  if (params.dossier) {
    const dossierId = String(params.dossier || '').trim();
    if (!dossierId || !planId) {
      setView(root, renderResearchError('Dossier', new Error('Dossier detail requires a plan and artifact id.')));
      return;
    }
    setView(root, renderResearchLoading('Dossier'));
    try {
      const artifact = await api.planArtifact(planId, dossierId);
      setView(root, renderDossierDetail(artifact, { planId }));
    } catch (err) {
      setView(root, renderResearchError('Dossier', err));
    }
    return;
  }

  if (params.dossiers != null) {
    setView(root, renderResearchLoading('Dossiers'));
    try {
      const lookup = await api.researchDossiers({ planId, limit: 10, includeContent: true });
      setView(root, renderDossierLookupSurface(lookup));
    } catch (err) {
      setView(root, renderResearchError('Dossiers', err));
    }
    return;
  }

  if (compareSymbols.length >= 2) {
    setView(root, renderResearchLoading(compareSymbols.join(' / '), 'compare'));
    try {
      const [compare, packets] = await Promise.all([
        api.researchCompare({ symbols: compareSymbols, period, interval, baseline_symbol: compareSymbols[0] }),
        Promise.all(compareSymbols.map(compareSymbol => api.researchEvidencePacket({
          symbol: compareSymbol,
          period,
          interval,
        }).catch(err => ({
          symbol: compareSymbol,
          provider: '',
          period,
          interval,
          generated_at: '',
          coverage: { warnings: [err?.message || 'Evidence packet unavailable.'] },
          freshness: { status: 'unavailable' },
          metrics: {},
          risk: {},
          quality: { confidence: 'low', coverage_score: 0, blocking_gaps: ['research:evidence_packet'] },
          provenance: {},
        })))),
      ]);
      setView(root, renderCompareSurface(compare, packets));
    } catch (err) {
      setView(root, renderResearchError(compareSymbols.join(' / '), err));
    }
    return;
  }

  if (!symbol) {
    setView(root, renderResearchEmpty());
    return;
  }

  setView(root, renderResearchLoading(symbol));
  try {
    const packet = await api.researchEvidencePacket({ symbol, period, interval });
    setView(root, renderResearchPage(packet, { requestedPacketId: params.packet || '' }));
  } catch (err) {
    setView(root, renderResearchError(symbol, err));
  }
}

export function normalizeCompareSymbols(value) {
  const parts = String(value || '')
    .split(/[\s,]+/)
    .map(part => part.trim().toUpperCase())
    .filter(Boolean);
  const seen = new Set();
  const symbols = [];
  for (const symbol of parts) {
    if (seen.has(symbol)) continue;
    seen.add(symbol);
    symbols.push(symbol);
    if (symbols.length >= 4) break;
  }
  return symbols;
}

export function renderResearchEmpty() {
  return html`
    <section class="hero-stack research-hero">
      <span class="hero-eyebrow">Research evidence</span>
      <h1 class="hero-number">Inspect a symbol</h1>
      <p class="hero-marginalia">Provider coverage, freshness, gaps, metrics, risk, and provenance live here before fit review turns them into personal context.</p>
    </section>
  `;
}

function renderResearchLoading(symbol, mode = 'evidence') {
  return html`
    <section class="hero-stack research-hero">
      <span class="hero-eyebrow">${mode === 'compare' ? 'Compare evidence' : 'Research evidence'}</span>
      <h1 class="hero-number">${symbol}</h1>
      <p class="hero-marginalia">Loading packet evidence.</p>
    </section>
  `;
}

function renderResearchError(symbol, err) {
  return html`
    <section class="hero-stack research-hero">
      <span class="hero-eyebrow">Research evidence</span>
      <h1 class="hero-number">${symbol}</h1>
      <p class="error-banner">${err?.message || 'Could not load research evidence.'}</p>
    </section>
  `;
}

function renderResearchPage(packet, { requestedPacketId = '' } = {}) {
  const packetId = String(packet?.packet_id || requestedPacketId || '').trim();
  return html`
    ${raw(renderEvidencePacket(packet))}
    <footer class="look-closer">
      <span class="section-eyebrow">Move through the loop</span>
      <div class="look-closer-row">
        <a class="link-editorial" href="#portfolio?fit=${encodeURIComponent(packet.symbol)}">Review fit</a>
        <a class="link-editorial" href="#copilot?intent=investment-fit">Discuss in Copilot</a>
        <a class="link-editorial" href="#research?dossiers=1">Dossiers</a>
        ${packetId ? html`<span class="marginalia">${packetId}</span>` : ''}
      </div>
    </footer>
  `;
}

export function renderEvidencePacket(packet) {
  if (!packet || typeof packet !== 'object') return renderResearchEmpty();
  return html`
    <section class="hero-stack research-hero">
      <span class="hero-eyebrow">Research evidence</span>
      <h1 class="hero-number">${packet.symbol}</h1>
      <p class="hero-marginalia">${packet.name || packet.asset_type || packet.provider || 'Evidence packet'}</p>
    </section>

    ${raw(renderEvidencePacketCard(packet))}
  `;
}

export function renderCompareSurface(compare, packets = []) {
  const symbols = normalizeCompareSymbols((compare?.symbols || []).join(','));
  const summary = compare?.summary || {};
  const items = Array.isArray(compare?.items) ? compare.items : [];
  const warnings = Array.isArray(compare?.warnings) ? compare.warnings : [];
  const packetBySymbol = new Map(
    packets
      .filter(packet => packet && typeof packet === 'object' && packet.symbol)
      .map(packet => [String(packet.symbol).toUpperCase(), packet])
  );
  return html`
    <section class="hero-stack research-hero">
      <span class="hero-eyebrow">Compare evidence</span>
      <h1 class="hero-number">${symbols.join(' / ') || 'Compare'}</h1>
      <p class="hero-marginalia">${compare?.provider || 'Provider'} · ${compare?.period || 'period'} · ${compare?.interval || 'interval'}</p>
    </section>

    <section class="research-packet" aria-label="Research compare">
      <header class="section-head">
        <span class="section-eyebrow">Small set comparison</span>
        <h2 class="section-title">Evidence ranking</h2>
      </header>
      <dl class="fit-meta research-meta">
        <div>
          <dt>Compared</dt>
          <dd>${summary.compared_symbols ?? items.length}</dd>
        </div>
        <div>
          <dt>Available</dt>
          <dd>${summary.available_symbols ?? items.filter(item => item.available).length}</dd>
        </div>
        <div>
          <dt>Baseline</dt>
          <dd>${summary.baseline_symbol || symbols[0] || 'Unknown'}</dd>
        </div>
        <div>
          <dt>Highest volatility</dt>
          <dd>${summary.highest_volatility_symbol || 'Unknown'}</dd>
        </div>
      </dl>

      <div class="research-compare-strip">
        ${items.slice(0, 4).map(item => raw(renderCompareRankItem(item, summary)))}
      </div>
      ${raw(renderListPanel('Warnings', warnings))}
      <div class="entry-actions">
        <a class="action-link muted" href="#research?dossiers=1">Dossiers <span class="arrow">→</span></a>
      </div>
    </section>

    <section class="research-compare-packets" aria-label="Compare evidence packets">
      ${symbols.map(symbol => raw(
        renderEvidencePacketCard(packetBySymbol.get(symbol) || compareItemToPacket(
          items.find(item => item.symbol === symbol),
          compare,
        ))
      ))}
    </section>
  `;
}

export function renderDossierLookupSurface(lookup = {}) {
  const items = Array.isArray(lookup.items) ? lookup.items : [];
  const warnings = Array.isArray(lookup.warnings) ? lookup.warnings : [];
  return html`
    <section class="hero-stack research-hero">
      <span class="hero-eyebrow">Research dossiers</span>
      <h1 class="hero-number">Saved evidence</h1>
      <p class="hero-marginalia">Saved research artifacts preserve thesis context, packet citations, and the trail back to provider evidence.</p>
    </section>

    <section class="research-packet" aria-label="Research dossiers">
      <header class="section-head">
        <span class="section-eyebrow">${lookup.plan_id || 'active plan'} · ${lookup.count ?? items.length} dossier${(lookup.count ?? items.length) === 1 ? '' : 's'}</span>
        <h2 class="section-title">Dossier lookup</h2>
      </header>
      ${items.length ? html`
        <div class="research-dossier-list">
          ${items.map(item => raw(renderDossierLookupItem(item)))}
        </div>
      ` : html`<p class="fit-empty">No saved research dossiers found for this plan.</p>`}
      ${raw(renderListPanel('Warnings', warnings))}
    </section>
  `;
}

function renderDossierLookupItem(item = {}) {
  const citations = parsePacketCitations(item.content_preview || '');
  const symbols = Array.isArray(item.symbols) ? item.symbols.filter(Boolean) : [];
  const planId = String(item.plan_id || '').trim();
  const artifactId = String(item.artifact_id || '').trim();
  const href = artifactId && planId
    ? `#research?dossier=${encodeURIComponent(artifactId)}&plan=${encodeURIComponent(planId)}`
    : '#research?dossiers=1';
  return html`
    <article class="research-dossier-item">
      <span>${fmtTimeShort(item.created_at) || item.file_name || 'Saved dossier'}</span>
      <h3>${item.title || artifactId || 'Research dossier'}</h3>
      ${symbols.length ? html`<p>${symbols.join(' · ')}</p>` : ''}
      ${raw(renderThesisReviewSummary(item.thesis_review))}
      <p>${citations.length} packet citation${citations.length === 1 ? '' : 's'}</p>
      <a class="action-link muted" href="${href}">Open dossier <span class="arrow">→</span></a>
    </article>
  `;
}

export function renderDossierDetail(artifact = {}, { planId = '' } = {}) {
  const content = String(artifact.content || '');
  const citations = parsePacketCitations(content);
  const symbols = Array.from(new Set(citations.map(citation => citation.symbol).filter(Boolean)));
  return html`
    <section class="hero-stack research-hero">
      <span class="hero-eyebrow">Dossier detail</span>
      <h1 class="hero-number">${symbols.join(' / ') || 'Dossier'}</h1>
      <p class="hero-marginalia">${artifact.title || artifact.file_name || 'Saved research artifact'}</p>
    </section>

    <section class="research-packet" aria-label="Research dossier detail">
      <header class="section-head">
        <span class="section-eyebrow">${planId || 'plan'} · ${fmtTimeShort(artifact.created_at) || 'saved artifact'}</span>
        <h2 class="section-title">${artifact.title || 'Research dossier'}</h2>
      </header>
      ${raw(renderThesisReviewSummary(artifact.thesis_review, { detail: true }))}
      ${citations.length ? html`
        <div class="fit-list">
          <h3>Packet citations</h3>
          <ul>${citations.map(citation => html`<li>${raw(renderPacketCitation(citation))}</li>`)}</ul>
        </div>
      ` : ''}
      ${symbols.length >= 2 ? html`
        <div class="entry-actions">
          <a class="action-link muted" href="#research?compare=${encodeURIComponent(symbols.slice(0, 4).join(','))}">
            Compare cited symbols <span class="arrow">→</span>
          </a>
        </div>
      ` : ''}
      <article class="research-dossier-markdown">
        ${raw(renderMarkdown(content))}
      </article>
    </section>
  `;
}

export function renderThesisReviewSurface({
  artifact = null,
  watchlistItem = null,
  recommendation = null,
  packet = null,
  planId = '',
  target = '',
  focusId = '',
  successMessage = '',
} = {}) {
  const content = String(artifact?.content || '');
  const citations = uniqueCitations([
    ...parsePacketCitations(content),
    ...packetCitationsFromEvidence(recommendation?.action_payload?.evidence),
  ]);
  const symbols = thesisReviewSymbols({ artifact, recommendation, target, citations });
  const evidence = recommendation?.action_payload?.evidence && typeof recommendation.action_payload.evidence === 'object'
    ? recommendation.action_payload.evidence
    : {};
  const review = artifact?.thesis_review && typeof artifact.thesis_review === 'object'
    ? artifact.thesis_review
    : watchlistThesisReview(watchlistItem) || thesisReviewFromEvidence(evidence);
  const status = String(review.status || evidence.thesis_review_status || '').trim().toLowerCase();
  const referencePrice = firstFiniteNumber(
    review.reference_price_usd,
    review.thesis_reference_price_usd,
    watchlistItem?.thesis_reference_price_usd,
    evidence.reference_price_usd,
    evidence.thesis_reference_price_usd,
  );
  const currentPrice = firstFiniteNumber(
    packet?.metrics?.last_price,
    evidence.current_price_usd,
    evidence.last_price,
  );
  const materialMovePct = firstFiniteNumber(
    evidence.material_price_change_pct,
    referencePrice && currentPrice ? ((currentPrice - referencePrice) / referencePrice) * 100 : null,
  );
  const hasReviewAction = Boolean(focusId || recommendation?.id);
  const recommendationId = focusId || recommendation?.id || '';
  const primarySymbol = symbols[0] || packet?.symbol || '';
  const compareHref = symbols.length >= 2
    ? `#research?compare=${encodeURIComponent(symbols.slice(0, 4).join(','))}`
    : '';
  const dossierHref = artifact && (artifact.id || artifact.artifact_id) && planId
    ? `#research?dossier=${encodeURIComponent(artifact.id || artifact.artifact_id)}&plan=${encodeURIComponent(planId)}`
    : '';
  const researchHref = primarySymbol
    ? `#research?symbol=${encodeURIComponent(primarySymbol)}${packet?.packet_id ? `&packet=${encodeURIComponent(packet.packet_id)}` : ''}`
    : '#research';
  const copilotHref = recommendationId
    ? `#copilot?focus=${encodeURIComponent(recommendationId)}&intent=investment-fit`
    : '#copilot?intent=investment-fit';
  const title = recommendation?.title || artifact?.title || artifact?.file_name || `${symbols.join(' / ') || 'Saved'} thesis review`;
  const detail = recommendation?.detail || evidence.summary || '';
  const thesisExcerpt = thesisExcerptFromMarkdown(content);
  const watchlistPanel = renderWatchlistThesisPanel(watchlistItem);
  const revisionHistory = Array.isArray(artifact?.thesis_revision_history)
    ? artifact.thesis_revision_history
    : Array.isArray(watchlistItem?.thesis_revision_history)
      ? watchlistItem.thesis_revision_history
      : [];

  return html`
    <section class="hero-stack research-hero">
      <span class="hero-eyebrow">Thesis review</span>
      <h1 class="hero-number">${symbols.join(' / ') || primarySymbol || 'Research thesis'}</h1>
      <p class="hero-marginalia">${title}</p>
    </section>

    <section class="research-packet" aria-label="Research thesis review">
      <header class="section-head">
        <span class="section-eyebrow">${planId || 'plan'} · ${status ? titleCase(status) : 'Review'} thesis</span>
        <h2 class="section-title">${title}</h2>
        ${detail ? html`<p class="marginalia">${detail}</p>` : ''}
      </header>

      ${raw(renderThesisReviewSummary(review, { detail: true }))}

      <dl class="fit-meta research-meta">
        <div>
          <dt>Status</dt>
          <dd>${status === 'expired' ? 'Review due' : titleCase(status || 'review')}</dd>
        </div>
        <div>
          <dt>Reference price</dt>
          <dd>${fmtUsd(referencePrice, { cents: true }) || 'Unknown'}</dd>
        </div>
        <div>
          <dt>Current price</dt>
          <dd>${fmtUsd(currentPrice, { cents: true }) || 'Unknown'}</dd>
        </div>
        <div>
          <dt>Material move</dt>
          <dd>${fmtPctSigned(materialMovePct) || 'Unknown'}</dd>
        </div>
      </dl>

      ${thesisExcerpt ? html`
        <article class="research-panel">
          <h3>Saved thesis</h3>
          <p>${thesisExcerpt}</p>
        </article>
      ` : ''}
      ${raw(watchlistPanel)}
      ${raw(renderThesisRevisionHistoryPanel(revisionHistory))}

      ${raw(renderPacketCitationPanel(citations))}
      ${packet ? raw(renderEvidencePacketCard(packet)) : ''}

      <div class="entry-actions">
        ${hasReviewAction ? html`
          <button class="action-link" data-action="complete-thesis-review" data-id="${recommendationId}">
            Mark thesis reviewed <span class="arrow">›</span>
          </button>
        ` : ''}
        <a class="action-link muted" href="${copilotHref}">Revise in Copilot <span class="arrow">→</span></a>
        ${dossierHref ? html`<a class="action-link muted" href="${dossierHref}">Open dossier <span class="arrow">→</span></a>` : ''}
        ${compareHref ? html`<a class="action-link muted" href="${compareHref}">Compare cited symbols <span class="arrow">→</span></a>` : ''}
        <a class="action-link muted" href="${researchHref}">Refresh evidence <span class="arrow">→</span></a>
      </div>
      <p class="marginalia thesis-review-status" aria-live="polite">${successMessage}</p>
    </section>
  `;
}

function renderThesisRevisionHistoryPanel(history = []) {
  const rows = Array.isArray(history)
    ? history.filter(item => item && typeof item === 'object').slice(0, 5)
    : [];
  if (!rows.length) return '';
  return html`
    <article class="research-panel thesis-revision-history-panel">
      <h3>Recent thesis revisions</h3>
      <ul>
        ${raw(rows.map(renderThesisRevisionHistoryItem).join(''))}
      </ul>
    </article>
  `;
}

function renderThesisRevisionHistoryItem(item = {}) {
  const reviewed = fmtTimeShort(item.reviewed_at) || String(item.reviewed_at || '').trim() || 'Recent review';
  const source = titleCase(String(item.source || '').replace(/_/g, ' ') || 'review');
  const revised = String(item.revised_thesis_excerpt || item.summary || '').trim();
  const prior = String(item.previous_thesis_excerpt || '').trim();
  const rationale = String(item.rationale_excerpt || '').trim();
  const gaps = Array.isArray(item.evidence_gaps) ? item.evidence_gaps.filter(Boolean).slice(0, 3) : [];
  const warnings = Array.isArray(item.warnings) ? item.warnings.filter(Boolean).slice(0, 3) : [];
  return html`
    <li>
      <p><strong>${reviewed}</strong> · ${source}</p>
      ${revised ? html`<p>${revised}</p>` : ''}
      ${prior ? html`<p class="marginalia">Previous: ${prior}</p>` : ''}
      ${rationale ? html`<p class="marginalia">${rationale}</p>` : ''}
      ${gaps.length ? html`<p class="marginalia">Gaps: ${gaps.join(' · ')}</p>` : ''}
      ${warnings.length ? html`<p class="marginalia">Warnings: ${warnings.join(' · ')}</p>` : ''}
    </li>
  `;
}

async function loadThesisReviewSurface(root, {
  reviewTarget = '',
  focusId = '',
  planId = '',
  artifactParam = '',
  period = '6mo',
  interval = '1d',
  successMessage = '',
} = {}) {
  setView(root, renderResearchLoading('Thesis review'));
  try {
    const recommendation = focusId
      ? await api.recommendation(focusId).catch(() => null)
      : null;
    const payload = recommendation?.action_payload && typeof recommendation.action_payload === 'object'
      ? recommendation.action_payload
      : {};
    const evidence = payload.evidence && typeof payload.evidence === 'object' ? payload.evidence : {};
    const suggestedAction = payload.suggested_action && typeof payload.suggested_action === 'object'
      ? payload.suggested_action
      : {};
    const artifactId = String(
      suggestedAction.artifact_id
      || evidence.artifact_id
      || artifactParam
      || (planId && reviewTarget && !isLikelySymbol(reviewTarget) ? reviewTarget : '')
    ).trim();
    const resolvedPlanId = String(planId || suggestedAction.plan_id || evidence.plan_id || recommendation?.plan_id || '').trim();
    const artifact = artifactId && resolvedPlanId
      ? await api.planArtifact(resolvedPlanId, artifactId).catch(() => null)
      : null;
    const symbols = thesisReviewSymbols({ artifact, recommendation, target: reviewTarget });
    const watchlistItem = !artifact
      ? await loadWatchlistItem(symbols[0] || reviewTarget, { period, interval }).catch(() => null)
      : null;
    const packet = symbols[0]
      ? await api.researchEvidencePacket({ symbol: symbols[0], period, interval }).catch(() => null)
      : null;
    setView(root, renderThesisReviewSurface({
      artifact,
      watchlistItem,
      recommendation,
      packet,
      planId: resolvedPlanId,
      target: reviewTarget,
      focusId,
      successMessage,
    }));
    bindThesisReviewActions(root, {
      recommendationId: focusId,
      reviewTarget,
      planId: resolvedPlanId,
      artifactParam: artifactId,
      period,
      interval,
    });
  } catch (err) {
    setView(root, renderResearchError('Thesis review', err));
  }
}

function renderThesisReviewSummary(review = {}, { detail = false } = {}) {
  if (!review || typeof review !== 'object') return '';
  const status = String(review.status || '').trim().toLowerCase();
  if (!status || status === 'unknown') return '';
  const age = Number(review.age_days);
  const ageLabel = Number.isFinite(age) ? `${Math.max(0, Math.round(age))} days old` : '';
  const expires = fmtTimeShort(review.expires_at);
  const reviewed = fmtTimeShort(review.reviewed_at);
  const label = status === 'expired' ? 'Review due' : 'Thesis current';
  const parts = [
    ageLabel,
    expires ? `Expires ${expires}` : '',
    detail && reviewed ? `Reviewed ${reviewed}` : '',
  ].filter(Boolean);
  return html`
    <p class="marginalia thesis-review ${status}">
      <span class="glyph">›</span> ${label}${parts.length ? ` · ${parts.join(' · ')}` : ''}
    </p>
  `;
}

function renderPacketCitation(citation) {
  const href = citation.symbol && citation.packet_id
    ? `#research?symbol=${encodeURIComponent(citation.symbol)}&packet=${encodeURIComponent(citation.packet_id)}`
    : '#research';
  const meta = [
    citation.provider,
    titleCase(citation.freshness),
    titleCase(citation.confidence),
    citation.coverage,
  ].filter(Boolean).join(' · ');
  return html`
    <a href="${href}">${citation.packet_id}</a>
    <span>${citation.symbol}${meta ? ` · ${meta}` : ''}</span>
  `;
}

function renderPacketCitationPanel(citations) {
  const visible = Array.isArray(citations) ? citations.filter(Boolean).slice(0, 12) : [];
  if (!visible.length) return '';
  return html`
    <div class="fit-list">
      <h3>Packet citations</h3>
      <ul>${visible.map(citation => html`<li>${raw(renderPacketCitation(citation))}</li>`)}</ul>
    </div>
  `;
}

function parsePacketCitations(markdown) {
  const lines = String(markdown || '').split(/\r?\n/);
  const citations = [];
  for (const line of lines) {
    if (!line.includes('research-evidence:')) continue;
    const cells = line.split('|').slice(1, -1).map(cell => cell.trim());
    const packetIndex = cells.findIndex(cell => cell.startsWith('research-evidence:'));
    if (packetIndex < 0) continue;
    citations.push({
      symbol: String(cells[0] || '').trim().toUpperCase(),
      packet_id: cells[packetIndex],
      provider: cells[packetIndex + 1] || '',
      freshness: cells[packetIndex + 2] || '',
      confidence: cells[packetIndex + 3] || '',
      coverage: cells[packetIndex + 4] || '',
      blocking_gaps: cells[packetIndex + 5] || '',
    });
  }
  return citations.slice(0, 12);
}

function thesisReviewSymbols({ artifact = null, recommendation = null, target = '', citations = null } = {}) {
  const evidence = recommendation?.action_payload?.evidence && typeof recommendation.action_payload.evidence === 'object'
    ? recommendation.action_payload.evidence
    : {};
  const suggestedAction = recommendation?.action_payload?.suggested_action && typeof recommendation.action_payload.suggested_action === 'object'
    ? recommendation.action_payload.suggested_action
    : {};
  const symbolValues = [
    suggestedAction.symbol,
    evidence.symbol,
    ...(Array.isArray(suggestedAction.symbols) ? suggestedAction.symbols : []),
    ...(Array.isArray(evidence.symbols) ? evidence.symbols : []),
    ...(Array.isArray(artifact?.symbols) ? artifact.symbols : []),
    ...((citations || parsePacketCitations(String(artifact?.content || ''))).map(citation => citation.symbol)),
    isLikelySymbol(target) ? target : '',
  ];
  const seen = new Set();
  return symbolValues
    .map(value => String(value || '').trim().toUpperCase())
    .filter(Boolean)
    .filter(value => {
      if (seen.has(value)) return false;
      seen.add(value);
      return true;
    })
    .slice(0, 8);
}

function thesisReviewFromEvidence(evidence = {}) {
  if (!evidence || typeof evidence !== 'object') return {};
  return {
    status: evidence.thesis_review_status,
    age_days: evidence.thesis_age_days || evidence.age_days,
    stale_after_days: evidence.stale_after_days,
    reviewed_at: evidence.thesis_reviewed_at || evidence.reviewed_at,
    expires_at: evidence.thesis_expires_at || evidence.expires_at,
    reference_price_usd: evidence.reference_price_usd || evidence.thesis_reference_price_usd,
  };
}

function watchlistThesisReview(item = null) {
  if (!item || typeof item !== 'object') return null;
  const reviewedAt = String(item.thesis_reviewed_at || item.reviewed_at || item.updated_at || item.created_at || '').trim();
  const expiresAt = String(item.thesis_expires_at || item.expires_at || '').trim();
  const reviewedDate = parseDate(reviewedAt);
  const expiresDate = parseDate(expiresAt);
  const now = Date.now();
  let status = '';
  if (expiresDate) status = expiresDate.getTime() <= now ? 'expired' : 'current';
  else if (reviewedDate) status = 'current';
  return {
    status,
    age_days: reviewedDate ? Math.max(0, Math.floor((now - reviewedDate.getTime()) / 86400000)) : null,
    stale_after_days: '',
    reviewed_at: reviewedAt,
    expires_at: expiresAt,
    reference_price_usd: item.thesis_reference_price_usd,
  };
}

function renderWatchlistThesisPanel(item = null) {
  if (!item || typeof item !== 'object') return '';
  const tags = Array.isArray(item.tags) ? item.tags.filter(Boolean).slice(0, 6) : [];
  const reasons = Array.isArray(item.watchlist_score_reasons)
    ? item.watchlist_score_reasons.filter(Boolean).slice(0, 4)
    : [];
  const score = firstFiniteNumber(item.watchlist_score_total);
  return html`
    <article class="research-panel watchlist-thesis-panel">
      <h3>Watchlist thesis</h3>
      ${item.thesis ? html`<p>${item.thesis}</p>` : html`<p>No saved watchlist thesis text yet.</p>`}
      ${item.note ? html`<p class="marginalia">${item.note}</p>` : ''}
      <dl>
        <div>
          <dt>Source</dt>
          <dd>${item.data_source || 'Watchlist'}</dd>
        </div>
        ${score != null ? html`
          <div>
            <dt>Watchlist score</dt>
            <dd>Score ${formatNumber(score)}</dd>
          </div>
        ` : ''}
        ${item.thesis_reviewed_at ? html`
          <div>
            <dt>Reviewed</dt>
            <dd>${fmtTimeShort(item.thesis_reviewed_at) || 'Unknown'}</dd>
          </div>
        ` : ''}
        ${item.thesis_expires_at ? html`
          <div>
            <dt>Expires</dt>
            <dd>${fmtTimeShort(item.thesis_expires_at) || 'Unknown'}</dd>
          </div>
        ` : ''}
      </dl>
      ${tags.length ? html`<p class="marginalia">${tags.join(' · ')}</p>` : ''}
      ${reasons.length ? raw(renderListPanel('Score reasons', reasons)) : ''}
    </article>
  `;
}

async function loadWatchlistItem(symbol, { period = '6mo', interval = '1d' } = {}) {
  const normalized = String(symbol || '').trim().toUpperCase();
  if (!normalized) return null;
  const payload = await api.watchlist({ period, interval, limit: 200, sort: 'symbol' });
  const items = Array.isArray(payload?.items) ? payload.items : [];
  return items.find(item => String(item?.symbol || '').trim().toUpperCase() === normalized) || null;
}

function parseDate(value) {
  const text = String(value || '').trim();
  if (!text) return null;
  const date = new Date(text);
  return Number.isNaN(date.getTime()) ? null : date;
}

function packetCitationsFromEvidence(evidence = {}) {
  if (!evidence || typeof evidence !== 'object') return [];
  const rawCitations = Array.isArray(evidence.packet_citations)
    ? evidence.packet_citations
    : [];
  return rawCitations
    .map(value => String(value || '').trim())
    .filter(Boolean)
    .map(packetId => ({
      symbol: packetId.split(':')[2]?.toUpperCase() || String(evidence.symbol || '').toUpperCase(),
      packet_id: packetId,
      provider: packetId.split(':')[1] || evidence.provider || '',
      freshness: evidence.freshness_status || '',
      confidence: evidence.confidence || '',
      coverage: evidence.coverage_score != null ? `${evidence.coverage_score}%` : '',
      blocking_gaps: '',
    }));
}

function uniqueCitations(citations) {
  const seen = new Set();
  return citations.filter(citation => {
    const key = `${citation.symbol}:${citation.packet_id}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 12);
}

function thesisExcerptFromMarkdown(markdown) {
  const text = String(markdown || '');
  const match = text.match(/## Thesis\s+([\s\S]*?)(?:\n## |\n# |$)/i);
  if (!match) return '';
  return match[1]
    .replace(/\[[^\]]+\]\([^)]+\)/g, '')
    .replace(/[#*_`>|-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 320);
}

function bindThesisReviewActions(root, {
  recommendationId = '',
  reviewTarget = '',
  planId = '',
  artifactParam = '',
  period = '6mo',
  interval = '1d',
} = {}) {
  if (!recommendationId) return;
  delegate(root, 'click', '[data-action="complete-thesis-review"]', async (event, button) => {
    event.preventDefault();
    const id = button.getAttribute('data-id') || recommendationId;
    if (!id) return;
    const status = $('.thesis-review-status', root);
    button.setAttribute('disabled', '');
    button.textContent = 'Refreshing thesis review...';
    if (status) status.textContent = '';
    try {
      await api.apply(id, {
        rationale: 'Reviewed research thesis in v2 Research; thesis metadata refreshed.',
        decision_status: 'reviewed',
        create_decision_packet: false,
        capture_scenario_diff: false,
        pin_research_bridge: false,
      });
      await loadThesisReviewSurface(root, {
        reviewTarget,
        focusId: id,
        planId,
        artifactParam,
        period,
        interval,
        successMessage: 'Review metadata refreshed. Today and Inbox can now use the updated thesis window.',
      });
    } catch (err) {
      button.removeAttribute('disabled');
      button.textContent = 'Mark thesis reviewed';
      if (status) status.textContent = err?.message || 'Could not refresh thesis metadata.';
    }
  });
}

function firstFiniteNumber(...values) {
  for (const value of values) {
    if (value == null || value === '') continue;
    const number = Number(value);
    if (Number.isFinite(number)) return number;
  }
  return null;
}

function isLikelySymbol(value) {
  return /^[A-Z][A-Z0-9.-]{0,9}$/i.test(String(value || '').trim());
}

export function renderEvidencePacketCard(packet) {
  if (!packet || typeof packet !== 'object') return '';
  const coverage = packet.coverage || {};
  const freshness = packet.freshness || {};
  const metrics = packet.metrics || {};
  const risk = packet.risk || {};
  const quality = packet.quality || {};
  const provenance = packet.provenance || {};
  const blockingGaps = Array.isArray(quality.blocking_gaps) ? quality.blocking_gaps : [];
  const warnings = [
    ...(Array.isArray(coverage.warnings) ? coverage.warnings : []),
    ...(Array.isArray(provenance.warnings) ? provenance.warnings : []),
  ].filter(Boolean);

  return html`
    <section class="research-packet" aria-label="Research evidence packet">
      <header class="section-head">
        <span class="section-eyebrow">${packet.symbol || 'symbol'} · ${packet.provider || 'provider'} · ${packet.period || 'period'} · ${packet.interval || 'interval'}</span>
        <h2 class="section-title">${packet.symbol || 'Research'} evidence packet</h2>
        ${packet.name ? html`<p class="marginalia">${packet.name}</p>` : ''}
      </header>

      <dl class="fit-meta research-meta">
        <div>
          <dt>Freshness</dt>
          <dd>${titleCase(freshness.status || 'unknown')}</dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd>${titleCase(quality.confidence || 'unknown')}</dd>
        </div>
        <div>
          <dt>Coverage</dt>
          <dd>${formatCoverageScore(quality.coverage_score)}</dd>
        </div>
        <div>
          <dt>Generated</dt>
          <dd>${fmtTimeShort(packet.generated_at) || 'Unknown'}</dd>
        </div>
      </dl>

      <div class="research-grid">
        ${raw(renderMetricPanel('Market metrics', [
          ['Last price', fmtUsd(metrics.last_price, { cents: true })],
          ['Period return', fmtPctSigned(metrics.period_change_pct)],
          ['Volatility', formatPct(metrics.volatility_pct)],
          ['Market cap', fmtUsd(metrics.market_cap_usd)],
          ['P/E', formatNumber(metrics.pe_ratio)],
          ['Dividend yield', formatPct(metrics.dividend_yield_pct)],
        ]))}
        ${raw(renderMetricPanel('Risk context', [
          ['Drawdown from high', fmtPctSigned(risk.drawdown_from_high_pct)],
          ['Quote as of', fmtTimeShort(freshness.quote_as_of) || 'Unknown'],
          ['History as of', fmtTimeShort(freshness.history_as_of) || 'Unknown'],
        ]))}
        ${raw(renderMetricPanel('Provider coverage', [
          ['Quote', coverage.quote_available ? 'Available' : 'Unavailable'],
          ['History', coverage.history_available ? 'Available' : 'Unavailable'],
          ['Provider status', titleCase(coverage.provider_status || freshness.status || 'unknown')],
          ['Endpoints', formatEndpoints(coverage.endpoints_attempted)],
        ]))}
      </div>

      ${raw(renderListPanel('Blocking gaps', blockingGaps))}
      ${raw(renderListPanel('Warnings', warnings))}
      <p class="marginalia">${packet.packet_id || ''}</p>
    </section>
  `;
}

function renderCompareRankItem(item = {}, summary = {}) {
  const relative = summary.baseline_relative_return_pct && typeof summary.baseline_relative_return_pct === 'object'
    ? summary.baseline_relative_return_pct[item.symbol]
    : null;
  return html`
    <article class="research-rank-item">
      <span>Rank ${item.rank || '—'}</span>
      <b>${item.symbol || 'Unknown'}</b>
      <p>Score ${formatNumber(item.score) || '—'} · ${titleCase(item.research_freshness_status || 'unknown')} · ${titleCase(item.research_confidence || 'unknown')}</p>
      ${relative != null ? html`<p>vs baseline ${fmtPctSigned(relative)}</p>` : ''}
    </article>
  `;
}

function compareItemToPacket(item = {}, compare = {}) {
  return {
    packet_id: item?.research_evidence_packet_id,
    symbol: item?.symbol || 'Unknown',
    provider: item?.research_provider || compare?.provider || '',
    period: compare?.period || '6mo',
    interval: compare?.interval || '1d',
    generated_at: compare?.generated_at,
    coverage: {
      quote_available: Number(item?.quote_records || 0) > 0,
      history_available: Number(item?.history_records || 0) > 0,
      warnings: [],
    },
    freshness: { status: item?.research_freshness_status || 'unknown' },
    metrics: {
      last_price: item?.last_price,
      period_change_pct: item?.period_change_pct,
      volatility_pct: item?.volatility_pct,
      market_cap_usd: item?.market_cap_usd,
      pe_ratio: item?.pe_ratio,
      dividend_yield_pct: item?.dividend_yield_pct,
    },
    risk: {},
    quality: {
      confidence: item?.research_confidence,
      coverage_score: item?.research_coverage_score,
      blocking_gaps: Array.isArray(item?.research_blocking_gaps) ? item.research_blocking_gaps : [],
    },
    provenance: { warnings: item?.message ? [item.message] : [] },
  };
}

function renderMetricPanel(title, rows) {
  const visible = rows.filter(([, value]) => value && value !== '—');
  if (!visible.length) return '';
  return html`
    <article class="research-panel">
      <h3>${title}</h3>
      <dl>
        ${visible.map(([label, value]) => html`
          <div>
            <dt>${label}</dt>
            <dd>${value}</dd>
          </div>
        `)}
      </dl>
    </article>
  `;
}

function renderListPanel(title, items) {
  const visible = Array.isArray(items) ? items.filter(Boolean).slice(0, 6) : [];
  if (!visible.length) return '';
  return html`
    <div class="fit-list">
      <h3>${title}</h3>
      <ul>${visible.map(item => html`<li>${humanText(item)}</li>`)}</ul>
    </div>
  `;
}

function formatCoverageScore(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 'Unknown';
  return `${number.toLocaleString('en-US', { maximumFractionDigits: 0 })}%`;
}

function formatPct(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '';
  return `${number.toLocaleString('en-US', { maximumFractionDigits: 1 })}%`;
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '';
  return number.toLocaleString('en-US', { maximumFractionDigits: 2 });
}

function formatEndpoints(value) {
  if (!Array.isArray(value) || !value.length) return '';
  return value.map(humanText).join(', ');
}

function humanText(value) {
  return String(value || '').replace(/[_-]+/g, ' ').trim();
}

function titleCase(value) {
  const text = humanText(value);
  if (!text) return '';
  return text.charAt(0).toUpperCase() + text.slice(1);
}
