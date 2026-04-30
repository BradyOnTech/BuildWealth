// Thread renderer for Copilot.
// Groups messages by date and renders user/assistant in distinct editorial vocab.

import { html, raw, esc } from '../../lib/dom.js';
import { renderMarkdown } from './markdown.js';

const TIME_FMT = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
const DAY_FMT = new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
const MONEY_FMT = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
const GOAL_DATE_FMT = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });

export function renderThread(messages, { thinking } = {}) {
  if (!messages.length && !thinking) return '';
  const groups = groupByDay(messages);
  const blocks = [];
  for (const [dayKey, items] of groups) {
    blocks.push(html`<div class="day-divider">${dayKey}</div>`);
    for (const m of items) blocks.push(renderMessage(m));
  }
  if (thinking) blocks.push(renderThinking());
  return html`<div class="thread">${blocks}</div>`;
}

function renderMessage(m) {
  const role = m.role === 'user' ? 'user' : 'assistant';
  const ts = m.created_at ? formatTime(m.created_at) : '';
  const tools = role === 'assistant' && Array.isArray(m.metadata?.tool_calls) ? m.metadata.tool_calls : [];

  const bodyHtml = role === 'user'
    ? esc(String(m.content || ''))
    : raw(renderMarkdown(String(m.content || '')));

  return html`
    <article class="message ${role}">
      <header class="message-eyebrow">
        <span class="role-tag">${role === 'user' ? 'You asked' : 'Copilot'}</span>
        ${ts ? html`<span class="timestamp">${ts}</span>` : ''}
      </header>
      <div class="message-body ${role}">${bodyHtml}</div>
      ${tools.length ? raw(renderToolTraces(tools)) : ''}
    </article>
  `;
}

function renderToolTraces(tools) {
  return html`
    <div class="tool-traces">
      ${tools.map(t => raw(renderToolTrace(t)))}
    </div>
  `;
}

function renderToolTrace(t) {
  if (isProfileDraftTrace(t)) {
    return renderProfileDraftCard(t.result);
  }
  if (isPortfolioFitTrace(t)) {
    return renderPortfolioFitCard(t.result);
  }
  if (isInvestmentRecommendationDraftTrace(t)) {
    return renderInvestmentRecommendationDraftCard(t.result);
  }
  if (isThesisRevisionTrace(t)) {
    return renderThesisRevisionCard(t.result);
  }
  if (isPlanReviewTrace(t)) {
    return renderPlanReviewCard(t.result);
  }
  if (isPlanScenarioDiffTrace(t)) {
    return renderPlanScenarioDiffCard(t.result);
  }
  return html`
    <details class="tool-trace">
      <summary>
        called <span class="tool-name">${esc(t.name || 'tool')}</span>
        ${t.error ? html`· <span style="color:var(--oxblood);">errored</span>` : ''}
      </summary>
      <pre>${esc(formatTrace(t))}</pre>
    </details>
  `;
}

function isProfileDraftTrace(trace) {
  return trace?.name === 'draft_financial_profile_update'
    && trace?.result?.draft_kind === 'financial_profile_update'
    && trace?.result?.proposed_profile;
}

function isPortfolioFitTrace(trace) {
  return trace?.name === 'assess_portfolio_fit'
    && trace?.result?.symbol
    && trace?.result?.fit_status;
}

function isInvestmentRecommendationDraftTrace(trace) {
  return trace?.name === 'draft_investment_research_recommendation'
    && trace?.result?.draft_kind === 'investment_research_recommendation'
    && trace?.result?.recommendation?.id;
}

function isThesisRevisionTrace(trace) {
  return (trace?.name === 'draft_watchlist_thesis_revision' || trace?.name === 'draft_dossier_thesis_revision')
    && (trace?.result?.draft_kind === 'watchlist_thesis_revision' || trace?.result?.draft_kind === 'dossier_thesis_revision')
    && trace?.result?.target
    && trace?.result?.proposed?.thesis;
}

function isPlanReviewTrace(trace) {
  return trace?.name === 'get_plan_review_context'
    && trace?.result?.plan_id;
}

function isPlanScenarioDiffTrace(trace) {
  return trace?.name === 'run_plan_scenario_diff'
    && trace?.result?.plan_id
    && Array.isArray(trace?.result?.scenario_deltas);
}

function renderPlanReviewCard(result = {}) {
  const planId = String(result.plan_id || '').trim();
  const title = String(result.title || planId || 'Plan').trim();
  const activeSet = result.active_assumption_set && typeof result.active_assumption_set === 'object'
    ? result.active_assumption_set
    : {};
  const healthSignals = Array.isArray(result.health_signals) ? result.health_signals.slice(0, 5) : [];
  const artifacts = Array.isArray(result.selected_artifacts) ? result.selected_artifacts.slice(0, 4) : [];
  const nextStep = result.suggested_next_step && typeof result.suggested_next_step === 'object'
    ? result.suggested_next_step
    : {};
  const nextSection = String(nextStep.section || healthSignals[0]?.section || 'assumptions').trim() || 'assumptions';

  return html`
    <article class="investment-fit-card plan-review-card">
      <div class="investment-fit-head">
        <div>
          <p class="profile-draft-eyebrow">Plan review context</p>
          <p class="investment-fit-title">${title}</p>
        </div>
        ${activeSet.name ? html`<p class="investment-fit-score">${activeSet.name}</p>` : ''}
      </div>
      <div class="investment-fit-meta-grid">
        ${renderFitMeta('Active set', activeSet.name || activeSet.id || 'Default')}
        ${renderFitMeta('Context scope', 'Bounded')}
      </div>
      ${renderPlanHealthSignals(planId, healthSignals)}
      ${renderPlanArtifacts(artifacts)}
      <div class="entry-actions">
        <a class="action-link" href="${planSectionHref(planId, nextSection)}">
          ${nextStep.label || 'Open Plan section'} <span class="arrow">→</span>
        </a>
      </div>
    </article>
  `;
}

function renderPlanHealthSignals(planId, signals) {
  if (!Array.isArray(signals) || !signals.length) {
    return html`
      <div class="profile-draft-section investment-fit-section">
        <p class="profile-draft-section-title">Plan health</p>
        <p>Plan context is decision-grade for this review.</p>
      </div>
    `;
  }
  return html`
    <div class="profile-draft-section investment-fit-section">
      <p class="profile-draft-section-title">Gaps found</p>
      <ul>
        ${signals.map(signal => {
          const section = String(signal?.section || 'assumptions').trim() || 'assumptions';
          return html`
            <li>
              <a href="${planSectionHref(planId, section)}">${signal?.title || 'Review plan context'}</a>
              ${signal?.detail ? html`<span> - ${signal.detail}</span>` : ''}
            </li>
          `;
        })}
      </ul>
    </div>
  `;
}

function renderPlanArtifacts(artifacts) {
  if (!Array.isArray(artifacts) || !artifacts.length) return '';
  return html`
    <div class="profile-draft-section investment-fit-section">
      <p class="profile-draft-section-title">Selected evidence</p>
      <ul>
        ${artifacts.map(artifact => {
          const citations = Array.isArray(artifact?.citations) ? artifact.citations.filter(Boolean).slice(0, 3) : [];
          return html`
            <li>
              <span>${artifact?.title || artifact?.id || 'Selected artifact'}</span>
              ${citations.length ? html`<p class="profile-draft-meta">${citations.join(' · ')}</p>` : ''}
            </li>
          `;
        })}
      </ul>
    </div>
  `;
}

function renderPlanScenarioDiffCard(result = {}) {
  const planId = String(result.plan_id || '').trim();
  const deltas = Array.isArray(result.scenario_deltas) ? result.scenario_deltas.slice(0, 3) : [];
  const monte = result.monte_carlo_delta && typeof result.monte_carlo_delta === 'object'
    ? result.monte_carlo_delta
    : {};
  const warnings = Array.isArray(result.warnings) ? result.warnings.filter(Boolean).slice(0, 3) : [];
  return html`
    <article class="investment-fit-card plan-review-card">
      <div class="investment-fit-head">
        <div>
          <p class="profile-draft-eyebrow">Plan scenario diff</p>
          <p class="investment-fit-title">Scenario compared</p>
        </div>
        ${Object.keys(monte).length ? html`<p class="investment-fit-score">Monte Carlo</p>` : ''}
      </div>
      <div class="investment-fit-meta-grid">
        ${deltas.map(delta => renderFitMeta(titleCase(delta?.label || 'scenario'), formatScenarioDelta(delta)))}
        ${renderFitMeta('Success probability', formatPercentSigned(monte.success_probability_delta))}
      </div>
      ${renderFitList('Warnings', warnings)}
      <div class="entry-actions">
        <a class="action-link" href="${planSectionHref(planId, 'scenarios')}">
          Open scenario workspace <span class="arrow">→</span>
        </a>
      </div>
    </article>
  `;
}

function renderThesisRevisionCard(result) {
  const target = result.target || {};
  const current = result.current || {};
  const proposed = result.proposed || {};
  const symbol = String(target.symbol || '').trim().toUpperCase();
  const source = String(target.data_source || 'OPENBB').trim().toUpperCase();
  const targetType = String(target.type || 'watchlist').trim().toLowerCase();
  const title = targetType === 'dossier'
    ? String(target.title || target.artifact_id || 'Saved dossier').trim()
    : `${symbol} · ${source}`;
  const payload = {
    target_type: targetType,
    symbol,
    data_source: source,
    plan_id: target.plan_id || '',
    artifact_id: target.artifact_id || '',
    thesis: proposed.thesis || '',
    note: proposed.note || '',
    reference_price_usd: proposed.reference_price_usd,
    thesis_reference_price_usd: proposed.reference_price_usd,
    review_window_days: proposed.review_window_days,
    tags: proposed.tags,
    rationale: result.rationale || '',
  };
  const encoded = encodeURIComponent(JSON.stringify(payload));
  return html`
    <article class="investment-fit-card thesis-draft-card">
      <div class="investment-fit-head">
        <div>
          <p class="profile-draft-eyebrow">Review thesis revision</p>
          <p class="investment-fit-title">${title}</p>
        </div>
        ${proposed.review_window_days ? html`<p class="investment-fit-score">${Number(proposed.review_window_days).toLocaleString('en-US')} days</p>` : ''}
      </div>
      ${current.thesis ? html`
        <div class="profile-draft-section investment-fit-section">
          <p class="profile-draft-section-title">Current thesis</p>
          <p>${current.thesis}</p>
          ${current.reference_price_usd != null ? html`<p class="profile-draft-meta">Reference ${MONEY_FMT.format(Number(current.reference_price_usd) || 0)}</p>` : ''}
        </div>
      ` : ''}
      <div class="profile-draft-section investment-fit-section">
        <p class="profile-draft-section-title">Proposed thesis</p>
        <p>${proposed.thesis}</p>
        ${proposed.note ? html`<p class="profile-draft-note">${proposed.note}</p>` : ''}
        <p class="profile-draft-meta">
          ${[
            proposed.reference_price_usd != null ? `Reference ${MONEY_FMT.format(Number(proposed.reference_price_usd) || 0)}` : '',
            proposed.review_window_days ? `Review window ${Number(proposed.review_window_days).toLocaleString('en-US')} days` : '',
          ].filter(Boolean).join(' · ')}
        </p>
      </div>
      ${result.rationale ? html`<p class="profile-draft-summary">${result.rationale}</p>` : ''}
      ${renderFitList('Evidence gaps', result.evidence_gaps)}
      ${renderFitList('Warnings', result.warnings)}
      <div class="entry-actions">
        <button class="action-link" data-thesis-draft="${encoded}">
          Save revised thesis <span class="arrow">›</span>
        </button>
      </div>
    </article>
  `;
}

function renderInvestmentRecommendationDraftCard(result) {
  const recommendation = result.recommendation || {};
  const actionPayload = recommendation.action_payload || {};
  const evidence = actionPayload.evidence || {};
  const suggestedAction = actionPayload.suggested_action || {};
  const quality = actionPayload.quality || {};
  const recommendationId = String(recommendation.id || '').trim();
  const symbol = String(evidence.symbol || suggestedAction.symbol || '').trim().toUpperCase();
  const meta = [
    symbol,
    evidence.freshness_status ? titleCase(evidence.freshness_status) : '',
    evidence.confidence ? titleCase(evidence.confidence) : '',
  ].filter(Boolean).join(' · ');
  const qualityLabels = [
    quality.actionability ? titleCase(quality.actionability) : '',
    quality.decision_grade ? 'Decision-grade' : '',
  ].filter(Boolean).join(' · ');

  return html`
    <article class="investment-fit-card">
      <div class="investment-fit-head">
        <div>
          <p class="profile-draft-eyebrow">Drafted investment review</p>
          <p class="investment-fit-title">${recommendation.title || 'Review investment research'}</p>
        </div>
        ${recommendation.priority ? html`<p class="investment-fit-score">${titleCase(recommendation.priority)}</p>` : ''}
      </div>
      ${meta ? html`<p class="profile-draft-meta">${meta}</p>` : ''}
      ${recommendation.detail ? html`<p class="profile-draft-summary">${recommendation.detail}</p>` : ''}
      <div class="investment-fit-meta-grid">
        ${renderFitMeta('Next step', titleCase(suggestedAction.kind || 'review_portfolio_fit'))}
        ${renderFitMeta('Quality', qualityLabels)}
      </div>
      ${recommendationId ? html`
        <div class="entry-actions">
          <a class="action-link" href="#inbox?focus=${recommendationId}">
            Open in Inbox <span class="arrow">→</span>
          </a>
        </div>
      ` : ''}
    </article>
  `;
}

function renderPortfolioFitCard(result) {
  const symbol = String(result.symbol || '').toUpperCase();
  const fitStatus = titleCase(result.fit_status);
  const nextStep = titleCase(result.recommended_next_step || 'review_context');
  const score = formatFitScore(result.fit_score);
  const evidence = result.evidence || {};
  const plan = result.plan_impact || {};
  const portfolio = result.portfolio_impact || {};
  const meta = [
    renderFitMeta('Next step', nextStep),
    renderFitMeta('Evidence', formatEvidenceStatus(evidence)),
    renderFitMeta('Plan horizon', formatPlanHorizon(plan)),
    renderFitMeta('Position', formatPortfolioPosition(portfolio)),
    renderFitMeta('Policy cap', formatPolicyCap(portfolio)),
    renderFitMeta('Policy', formatPolicyGuardrails(portfolio.investment_policy)),
    renderFitMeta('Sector policy', formatSectorPolicy(portfolio)),
    renderFitMeta('Account location', formatAccountLocationSummary(portfolio.account_location)),
    renderFitMeta('Proposed account', formatProposedAccount(portfolio.proposed_account)),
  ].filter(Boolean);

  return html`
    <article class="investment-fit-card">
      <div class="investment-fit-head">
        <div>
          <p class="profile-draft-eyebrow">Investment-fit review</p>
          <p class="investment-fit-title">${symbol} · ${fitStatus}</p>
        </div>
        ${score ? html`<p class="investment-fit-score">${score}</p>` : ''}
      </div>
      <div class="investment-fit-meta-grid">
        ${meta}
      </div>
      ${renderFitList('Why it matters', result.fit_reasons)}
      ${renderFitList('Risks to review', result.fit_risks)}
      ${renderAccountLocationList(portfolio.account_location)}
      ${renderFitList('Blocking gaps', result.blocking_gaps)}
      ${renderEvidencePacketLink(symbol, evidence)}
    </article>
  `;
}

function renderFitMeta(label, value) {
  if (!value) return '';
  return html`
    <div class="investment-fit-meta">
      <span>${label}</span>
      <b>${value}</b>
    </div>
  `;
}

function renderFitList(title, items) {
  if (!Array.isArray(items) || !items.length) return '';
  return html`
    <div class="profile-draft-section investment-fit-section">
      <p class="profile-draft-section-title">${title}</p>
      <ul>
        ${items.slice(0, 4).map(item => html`<li>${item}</li>`)}
      </ul>
    </div>
  `;
}

function renderEvidencePacketLink(symbol, evidence = {}) {
  const packetId = String(evidence.packet_id || evidence.research_evidence_packet_id || '').trim();
  if (!packetId) return '';
  const href = symbol
    ? `#research?symbol=${encodeURIComponent(symbol)}&packet=${encodeURIComponent(packetId)}`
    : '#research';
  return html`
    <p class="profile-draft-meta">
      Evidence packet <a href="${href}">${packetId}</a>
    </p>
  `;
}

function renderAccountLocationList(accountLocation = {}) {
  const accounts = Array.isArray(accountLocation?.accounts)
    ? accountLocation.accounts.filter(Boolean).slice(0, 3)
    : [];
  const warnings = Array.isArray(accountLocation?.warnings)
    ? accountLocation.warnings.filter(Boolean).slice(0, 2)
    : [];
  if (!accounts.length && !warnings.length) return '';
  const rows = [
    ...accounts.map(formatAccountLocationRow),
    ...warnings,
  ];
  return renderFitList('Account and tax context', rows);
}

function renderProfileDraftCard(result) {
  const profile = result.proposed_profile || {};
  const sections = [
    renderItemSection('Income items', profile.income_items, 'monthly_amount_usd'),
    renderItemSection('Expense items', profile.expense_items, 'monthly_amount_usd'),
    renderItemSection('Debt items', profile.debt_items, 'balance_usd'),
    renderGoalSection(profile.goal_items),
    renderTaxSection(profile.tax_profile),
    renderInvestmentPolicySection(profile.investment_policy),
    renderPhysicalAssetSection(profile.physical_assets),
  ].filter(Boolean);
  const flagLine = profile.flags?.no_debt
    ? html`<p class="profile-draft-flag">No debt</p>`
    : '';
  const draftPayload = result.patch_payload || profile;
  const encoded = encodeURIComponent(JSON.stringify(draftPayload));

  return html`
    <article class="profile-draft-card">
      <p class="profile-draft-eyebrow">Review profile update</p>
      <p class="profile-draft-summary">${result.summary || 'Copilot drafted changes for your financial profile.'}</p>
      ${raw(sections.join(''))}
      ${raw(flagLine)}
      <div class="entry-actions">
        <button class="action-link" data-profile-draft="${encoded}">
          Apply profile update <span class="arrow">›</span>
        </button>
      </div>
    </article>
  `;
}

function renderItemSection(title, items, amountKey) {
  if (!Array.isArray(items) || !items.length) return '';
  return html`
    <div class="profile-draft-section">
      <p class="profile-draft-section-title">${title}</p>
      <ul>
        ${items.slice(0, 4).map(item => html`
          <li>
            <span>${item?.label || 'Untitled'}</span>
            ${item?.[amountKey] != null ? html`<b>${MONEY_FMT.format(Number(item[amountKey]) || 0)}</b>` : ''}
          </li>
        `)}
      </ul>
    </div>
  `;
}

function renderGoalSection(items) {
  if (!Array.isArray(items) || !items.length) return '';
  return html`
    <div class="profile-draft-section">
      <p class="profile-draft-section-title">Goal items</p>
      <ul>
        ${items.slice(0, 4).map(item => {
          const amount = item?.target_amount_usd != null
            ? MONEY_FMT.format(Number(item.target_amount_usd) || 0)
            : '';
          const details = [
            item?.target_date ? `Target ${formatGoalDate(item.target_date)}` : '',
            item?.priority ? `${titleCase(item.priority)} priority` : '',
          ].filter(Boolean);
          return html`
            <li class="profile-draft-goal">
              <div class="profile-draft-goal-row">
                <span>${item?.label || 'Untitled goal'}</span>
                ${amount ? html`<b>${amount}</b>` : ''}
              </div>
              ${details.length ? html`<p class="profile-draft-meta">${details.join(' · ')}</p>` : ''}
              ${item?.notes ? html`<p class="profile-draft-note">${item.notes}</p>` : ''}
            </li>
          `;
        })}
      </ul>
    </div>
  `;
}

function renderPhysicalAssetSection(items) {
  if (!Array.isArray(items) || !items.length) return '';
  return html`
    <div class="profile-draft-section">
      <p class="profile-draft-section-title">Physical assets</p>
      <ul>
        ${items.slice(0, 4).map(item => {
          const amount = item?.current_value_usd != null
            ? MONEY_FMT.format(Number(item.current_value_usd) || 0)
            : '';
          const details = [
            item?.asset_type ? titleCase(item.asset_type) : '',
            item?.purchase_date ? `Purchased ${formatGoalDate(item.purchase_date)}` : '',
            item?.annual_growth_rate != null ? `Growth ${formatPercent(item.annual_growth_rate)}/yr` : '',
          ].filter(Boolean);
          return html`
            <li class="profile-draft-asset">
              <div class="profile-draft-asset-row">
                <span>${item?.label || 'Untitled asset'}</span>
                ${amount ? html`<b>${amount}</b>` : ''}
              </div>
              ${details.length ? html`<p class="profile-draft-meta">${details.join(' · ')}</p>` : ''}
            </li>
          `;
        })}
      </ul>
    </div>
  `;
}

function renderTaxSection(taxProfile) {
  if (!taxProfile || typeof taxProfile !== 'object') return '';
  const filingStatus = String(taxProfile.filing_status || '').trim();
  const marginalTaxRate = taxProfile.marginal_tax_rate;
  const state = String(taxProfile.state || '').trim().toUpperCase();
  if (!filingStatus && marginalTaxRate == null && !state) return '';

  const details = [
    marginalTaxRate != null ? `Marginal ${formatPercent(marginalTaxRate)}` : '',
    state ? `State ${state}` : '',
  ].filter(Boolean);

  return html`
    <div class="profile-draft-section">
      <p class="profile-draft-section-title">Tax profile</p>
      <ul>
        <li class="profile-draft-tax">
          <span>${filingStatus ? titleCase(filingStatus) : 'Tax basics'}</span>
          ${details.length ? html`<p class="profile-draft-meta">${details.join(' · ')}</p>` : ''}
        </li>
      </ul>
    </div>
  `;
}

function renderInvestmentPolicySection(policy) {
  if (!policy || typeof policy !== 'object') return '';
  const maxSingle = policy.max_single_symbol_exposure_pct;
  const maxSector = policy.max_sector_exposure_pct;
  const confidence = String(policy.minimum_research_confidence || '').trim();
  const cashFloor = policy.minimum_cash_runway_months;
  const assetClassCaps = formatAssetClassCaps(policy.max_asset_class_exposure_pct, 'Asset-class cap');
  const simplicity = String(policy.simplicity_preference || '').trim();
  const taxSensitivity = String(policy.tax_sensitivity || '').trim();
  const riskTolerance = String(policy.risk_tolerance || '').trim();
  const restrictedSymbols = Array.isArray(policy.restricted_symbols) ? policy.restricted_symbols.filter(Boolean) : [];
  const restrictedSectors = Array.isArray(policy.restricted_sectors) ? policy.restricted_sectors.filter(Boolean) : [];
  if (
    maxSingle == null
    && maxSector == null
    && !confidence
    && cashFloor == null
    && !assetClassCaps
    && !simplicity
    && !taxSensitivity
    && !riskTolerance
    && !restrictedSymbols.length
    && !restrictedSectors.length
  ) return '';

  const details = [
    maxSingle != null ? `Max single symbol ${Number(maxSingle).toFixed(0)}%` : '',
    maxSector != null ? `Max sector ${Number(maxSector).toFixed(0)}%` : '',
    confidence ? `Research confidence ${titleCase(confidence)}` : '',
    cashFloor != null ? `Cash floor ${Number(cashFloor).toLocaleString('en-US', { maximumFractionDigits: 1 })} mo` : '',
    assetClassCaps,
    simplicity ? `Simplicity ${titleCase(simplicity)}` : '',
    taxSensitivity ? `Tax sensitivity ${titleCase(taxSensitivity)}` : '',
    riskTolerance ? `Risk ${titleCase(riskTolerance)}` : '',
    restrictedSymbols.length ? `Avoid ${restrictedSymbols.slice(0, 2).join(', ')}` : '',
    restrictedSectors.length ? `Avoid sectors ${restrictedSectors.slice(0, 2).map(titleCase).join(', ')}` : '',
  ].filter(Boolean);

  return html`
    <div class="profile-draft-section">
      <p class="profile-draft-section-title">Investment policy</p>
      <ul>
        <li class="profile-draft-tax">
          <span>Rules of the road</span>
          ${details.length ? html`<p class="profile-draft-meta">${details.join(' · ')}</p>` : ''}
        </li>
      </ul>
    </div>
  `;
}

function formatGoalDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return GOAL_DATE_FMT.format(date);
}

function titleCase(value) {
  const text = String(value || '').replace(/[_-]+/g, ' ').trim();
  if (!text) return '';
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function formatPercent(value) {
  const percent = Number(value) * 100;
  if (!Number.isFinite(percent)) return String(value);
  return `${percent.toLocaleString('en-US', { maximumFractionDigits: 2 })}%`;
}

function formatFitScore(value) {
  const score = Number(value);
  if (!Number.isFinite(score)) return '';
  return `${Math.round(score)}/100`;
}

function formatEvidenceStatus(evidence) {
  const parts = [
    evidence?.freshness_status ? titleCase(evidence.freshness_status) : '',
    evidence?.confidence ? titleCase(evidence.confidence) : '',
  ].filter(Boolean);
  return parts.join(' · ');
}

function formatPlanHorizon(plan) {
  const parts = [
    plan?.time_horizon ? titleCase(plan.time_horizon) : '',
    Number.isFinite(Number(plan?.years)) ? `${Number(plan.years).toLocaleString('en-US', { maximumFractionDigits: 1 })}y` : '',
  ].filter(Boolean);
  return parts.join(' · ');
}

function formatPortfolioPosition(portfolio) {
  if (!portfolio || typeof portfolio !== 'object') return '';
  if (portfolio.current_weight_pct != null) {
    const weight = Number(portfolio.current_weight_pct);
    if (Number.isFinite(weight)) {
      return `${weight.toLocaleString('en-US', { maximumFractionDigits: 1 })}% held`;
    }
  }
  if (portfolio.existing_position === false) return 'Not held';
  if (portfolio.existing_position === true) return 'Held';
  return '';
}

function formatPolicyCap(portfolio) {
  if (!portfolio || typeof portfolio !== 'object') return '';
  const cap = Number(portfolio.single_holding_max_pct);
  if (!Number.isFinite(cap)) return '';
  const source = portfolio.single_holding_policy_source === 'profile.investment_policy'
    ? 'Personal policy'
    : 'Portfolio policy';
  return `${cap.toLocaleString('en-US', { maximumFractionDigits: 1 })}% · ${source}`;
}

function formatPolicyGuardrails(policy) {
  if (!policy || typeof policy !== 'object') return '';
  const restrictedSymbols = Array.isArray(policy.restricted_symbols) ? policy.restricted_symbols.filter(Boolean) : [];
  const restrictedSectors = Array.isArray(policy.restricted_sectors) ? policy.restricted_sectors.filter(Boolean) : [];
  const parts = [
    policy.minimum_research_confidence ? `Research ${titleCase(policy.minimum_research_confidence)}` : '',
    policy.minimum_cash_runway_months != null ? `Cash floor ${Number(policy.minimum_cash_runway_months).toLocaleString('en-US', { maximumFractionDigits: 1 })} mo` : '',
    formatAssetClassCaps(policy.max_asset_class_exposure_pct, 'Asset cap'),
    policy.simplicity_preference ? `Simplicity ${titleCase(policy.simplicity_preference)}` : '',
    policy.tax_sensitivity ? `Tax ${titleCase(policy.tax_sensitivity)}` : '',
    policy.risk_tolerance ? `Risk ${titleCase(policy.risk_tolerance)}` : '',
    policy.max_sector_exposure_pct != null ? `Sector cap ${Number(policy.max_sector_exposure_pct).toLocaleString('en-US', { maximumFractionDigits: 1 })}%` : '',
    restrictedSymbols.length ? `Avoid ${restrictedSymbols.slice(0, 2).join(', ')}` : '',
    restrictedSectors.length ? `Avoid ${restrictedSectors.slice(0, 2).map(titleCase).join(', ')}` : '',
  ].filter(Boolean);
  return parts.join(' · ');
}

function formatAssetClassCaps(caps, label) {
  if (!caps || typeof caps !== 'object' || Array.isArray(caps)) return '';
  const rows = Object.entries(caps)
    .filter(([, value]) => Number.isFinite(Number(value)))
    .slice(0, 2)
    .map(([key, value]) => `${titleCase(key)} ${Number(value).toLocaleString('en-US', { maximumFractionDigits: 1 })}%`);
  return rows.length ? `${label} ${rows.join(', ')}` : '';
}

function formatSectorPolicy(portfolio) {
  if (!portfolio || typeof portfolio !== 'object') return '';
  const sector = String(portfolio.candidate_sector || '').trim();
  const weight = Number(portfolio.sector_weight_after_trade_pct);
  const cap = Number(portfolio.sector_max_pct);
  if (!sector || !Number.isFinite(weight) || !Number.isFinite(cap)) return '';
  return `${sector} ${weight.toLocaleString('en-US', { maximumFractionDigits: 1 })}% · cap ${cap.toLocaleString('en-US', { maximumFractionDigits: 1 })}%`;
}

function formatAccountLocationSummary(accountLocation) {
  if (!accountLocation || typeof accountLocation !== 'object') return '';
  const treatments = Array.isArray(accountLocation.tax_treatments)
    ? accountLocation.tax_treatments.filter(Boolean).map(titleCase)
    : [];
  const lotCoverage = String(accountLocation.tax_lot_coverage || '').trim();
  const parts = [
    treatments.join(', '),
    lotCoverage && lotCoverage !== 'known' && lotCoverage !== 'not_applicable'
      ? `Tax lots ${titleCase(lotCoverage).toLowerCase()}`
      : '',
  ].filter(Boolean);
  return parts.join(' · ');
}

function formatProposedAccount(account) {
  if (!account || typeof account !== 'object') return '';
  const preferred = Array.isArray(account.policy_preferred_treatments)
    ? account.policy_preferred_treatments.filter(Boolean)
    : [];
  return [
    account.account_name || account.account_id || '',
    formatTreatmentLabel(account.tax_treatment || account.account_type || ''),
    preferred.length ? `prefers ${preferred.map(formatTreatmentLabel).join(', ')}` : '',
  ].filter(Boolean).join(' · ');
}

function formatTreatmentLabel(value) {
  return String(value || '')
    .replace(/[_-]+/g, ' ')
    .trim()
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

function formatAccountLocationRow(account = {}) {
  const gainLoss = account.unrealized_gain_loss_usd != null
    ? `${MONEY_FMT.format(Number(account.unrealized_gain_loss_usd) || 0)} gain/loss`
    : '';
  return [
    account.account_name || account.account_id || 'Unknown account',
    titleCase(account.tax_treatment || account.account_type || 'unknown'),
    gainLoss,
    account.lot_term_mix ? `${titleCase(account.lot_term_mix)} lots` : '',
  ].filter(Boolean).join(' · ');
}

function planSectionHref(planId, section) {
  const id = String(planId || '').trim();
  const safeSection = encodeURIComponent(String(section || '').trim() || 'assumptions');
  return id
    ? `#plan?id=${encodeURIComponent(id)}&section=${safeSection}`
    : `#plan?section=${safeSection}`;
}

function formatScenarioDelta(delta = {}) {
  const parts = [
    delta.delta_future_value_usd != null ? `Future ${formatMoneySigned(delta.delta_future_value_usd)}` : '',
    delta.delta_real_value_usd != null ? `Real ${formatMoneySigned(delta.delta_real_value_usd)}` : '',
  ].filter(Boolean);
  return parts.join(' · ');
}

function formatMoneySigned(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '';
  const sign = number > 0 ? '+' : '';
  return `${sign}${MONEY_FMT.format(number)}`;
}

function formatPercentSigned(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '';
  const sign = number > 0 ? '+' : '';
  return `${sign}${(number * 100).toLocaleString('en-US', { maximumFractionDigits: 1 })}%`;
}

function formatTrace(trace) {
  const lines = [];
  if (trace.arguments && Object.keys(trace.arguments).length) {
    lines.push('// arguments');
    lines.push(JSON.stringify(trace.arguments, null, 2));
  }
  if (trace.error) {
    lines.push('');
    lines.push('// error');
    lines.push(String(trace.error));
  } else if (trace.result && Object.keys(trace.result || {}).length) {
    lines.push('');
    lines.push('// result');
    lines.push(JSON.stringify(trace.result, null, 2));
  }
  return lines.join('\n') || '(no payload)';
}

function renderThinking() {
  return html`
    <div class="thinking-line">
      <span class="role-tag" style="font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:0.18em;color:var(--gilt);">Copilot</span>
      <span>is thinking</span>
      <span class="dots"><span>·</span><span>·</span><span>·</span></span>
    </div>
  `;
}

function formatTime(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return TIME_FMT.format(d);
}

function groupByDay(messages) {
  const groups = new Map();
  for (const m of messages) {
    const d = m.created_at ? new Date(m.created_at) : new Date();
    const key = Number.isNaN(d.getTime()) ? 'today' : DAY_FMT.format(d);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(m);
  }
  return groups;
}
