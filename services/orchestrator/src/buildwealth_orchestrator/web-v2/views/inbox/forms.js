// Inline forms for Apply / Decline / Outcome.
// Forms render inside the entry that owns them. Submission is wired
// in inbox.js via delegated event handlers.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtUsdSigned } from '../../lib/format.js';

export function renderInlineForm(item, expanded, ctx) {
  const { mode, busy, preview, error } = expanded;
  if (mode === 'apply')   return renderApplyForm(item, { busy, preview, error });
  if (mode === 'decline') return renderDeclineForm(item, { busy, error });
  if (mode === 'outcome') return renderOutcomeForm(item, { busy, error });
  return '';
}

function renderApplyForm(item, { busy, preview, error }) {
  return html`
    <div class="inline-form" data-form="apply" data-id="${item.id}">
      <p class="inline-form-title">Apply this suggestion?</p>
      ${raw(renderPreview(preview))}
      <div class="inline-form-row">
        <label class="inline-label" for="apply-rationale-${item.id}">Rationale (optional)</label>
        <textarea id="apply-rationale-${item.id}" name="rationale"
          placeholder="Why now? Anything to remember about this decision."></textarea>
      </div>
      ${error ? html`<p class="inline-warning">${error}</p>` : ''}
      <div class="inline-form-actions">
        <button class="btn btn-primary" data-submit="apply" data-id="${item.id}" ${busy ? 'disabled' : ''}>
          ${busy ? 'Applying…' : 'Yes, apply'}
        </button>
        <button class="btn btn-ghost" data-cancel data-id="${item.id}" ${busy ? 'disabled' : ''}>Cancel</button>
      </div>
    </div>
  `;
}

function renderDeclineForm(item, { busy, error }) {
  return html`
    <div class="inline-form danger" data-form="decline" data-id="${item.id}">
      <p class="inline-form-title">Decline this suggestion?</p>
      <div class="inline-form-row">
        <label class="inline-label" for="decline-reason-${item.id}">Reason (optional)</label>
        <textarea id="decline-reason-${item.id}" name="reason"
          placeholder="Why this isn't right — useful when calibration revisits this later."></textarea>
      </div>
      ${error ? html`<p class="inline-warning">${error}</p>` : ''}
      <div class="inline-form-actions">
        <button class="btn btn-primary" data-submit="decline" data-id="${item.id}" ${busy ? 'disabled' : ''}>
          ${busy ? 'Declining…' : 'Yes, decline'}
        </button>
        <button class="btn btn-ghost" data-cancel data-id="${item.id}" ${busy ? 'disabled' : ''}>Cancel</button>
      </div>
    </div>
  `;
}

function renderOutcomeForm(item, { busy, error }) {
  const nowLocal = toLocalDatetime(new Date());
  const guidance = outcomeGuidance(item);
  return html`
    <div class="inline-form muted" data-form="outcome" data-id="${item.id}">
      <p class="inline-form-title">${guidance.title}</p>
      ${guidance.summary ? html`<p class="marginalia">${guidance.summary}</p>` : ''}
      ${guidance.calibrationDomain ? html`
        <input type="hidden" name="process_outcome" value="" />
        <input type="hidden" name="evidence_sufficiency" value="" />
      ` : ''}
      ${guidance.presets.length ? html`
        <div class="inline-form-row">
          <label class="inline-label">Outcome cues</label>
          <div class="entry-actions">
            ${raw(guidance.presets.map(rawPreset => {
              const preset = normalizeOutcomePreset(rawPreset);
              return `
              <button class="action-link muted" type="button" data-outcome-preset="${esc(preset.label)}"${preset.code ? ` data-outcome-code="${esc(preset.code)}"` : ''}${preset.evidence ? ` data-evidence-sufficiency="${esc(preset.evidence)}"` : ''}>
                ${esc(preset.label)}
              </button>
            `;
            }).join(''))}
          </div>
        </div>
      ` : ''}
      <div class="inline-form-row cols-2">
        <div>
          <label class="inline-label" for="outcome-fv-${item.id}">Future-value delta (USD)</label>
          <input id="outcome-fv-${item.id}" name="future_value_delta_usd" type="number" step="any" placeholder="+12500" />
        </div>
        <div>
          <label class="inline-label" for="outcome-rv-${item.id}">Real-value delta (USD)</label>
          <input id="outcome-rv-${item.id}" name="real_value_delta_usd" type="number" step="any" placeholder="+8400" />
        </div>
      </div>
      <div class="inline-form-row cols-2">
        <div>
          <label class="inline-label" for="outcome-when-${item.id}">Observed at</label>
          <input id="outcome-when-${item.id}" name="observed_at" type="datetime-local" value="${nowLocal}" />
        </div>
        <div>
          <label class="inline-label" for="outcome-window-${item.id}">Window (days)</label>
          <input id="outcome-window-${item.id}" name="measurement_window_days" type="number" step="1" placeholder="30" />
        </div>
      </div>
      <div class="inline-form-row">
        <label class="inline-label" for="outcome-source-${item.id}">Measurement source</label>
        <input id="outcome-source-${item.id}" name="measurement_source" type="text" placeholder="${guidance.measurementPlaceholder}" />
      </div>
      <div class="inline-form-row">
        <label class="inline-label" for="outcome-note-${item.id}">Note (optional)</label>
        <textarea id="outcome-note-${item.id}" name="outcome_note" placeholder="${guidance.notePlaceholder}"></textarea>
      </div>
      ${error ? html`<p class="inline-warning">${error}</p>` : ''}
      <div class="inline-form-actions">
        <button class="btn btn-primary" data-submit="outcome" data-id="${item.id}" ${busy ? 'disabled' : ''}>
          ${busy ? 'Saving…' : 'Save outcome'}
        </button>
        <button class="btn btn-ghost" data-cancel data-id="${item.id}" ${busy ? 'disabled' : ''}>Cancel</button>
      </div>
    </div>
  `;
}

function outcomeGuidance(item) {
  const source = String(item?.source || '').toLowerCase();
  const type = String(item?.recommendation_type || '').toLowerCase();
  const quality = item?.action_payload?.quality || {};
  const actionability = String(quality.actionability || '').toLowerCase();
  const generator = item?.action_payload?.generator || {};
  const thesisRevision = item?.action_payload?.thesis_revision && typeof item.action_payload.thesis_revision === 'object'
    ? item.action_payload.thesis_revision
    : null;
  const isInvestmentResearch = source === 'copilot:investment_fit'
    || source.includes('watchlist_research')
    || generator.signal_type === 'investment_fit_discussion'
    || quality.calibration?.domain === 'investment_research';
  if (isInvestmentResearch) {
    const thesisTarget = thesisRevision
      ? String(thesisRevision.symbol || thesisRevision.artifact_id || thesisRevision.target_type || '').trim()
      : '';
    return {
      title: 'Did the investment-fit review help?',
      summary: thesisTarget
        ? `This outcome will calibrate the thesis revision for ${thesisTarget}.`
        : '',
      calibrationDomain: 'investment_research',
      presets: [
        { label: 'Useful review', code: 'useful_review', evidence: 'sufficient' },
        { label: 'Evidence insufficient', code: 'insufficient_evidence', evidence: 'insufficient' },
        { label: 'Deferred', code: 'deferred', evidence: 'partial' },
        { label: 'Acted elsewhere', code: 'acted_elsewhere', evidence: 'sufficient' },
        { label: 'Not useful', code: 'not_useful', evidence: 'not_reviewed' },
      ],
      measurementPlaceholder: 'copilot investment review',
      notePlaceholder: 'decision clarified, evidence missing, deferred, acted elsewhere, not useful',
    };
  }
  if (source.includes('stale_assumptions')) {
    return {
      title: 'What changed after the assumption review?',
      summary: 'Record which assumptions were reviewed and whether any follow-up recommendations should be regenerated.',
      presets: ['Assumptions reviewed', 'Changes made', 'Follow-up needed'],
      measurementPlaceholder: 'manual assumption review',
      notePlaceholder: 'reviewed assumptions, changes made, follow-up needed',
    };
  }
  if (actionability === 'context_gathering' || source.includes('profile_completeness')) {
    return {
      title: 'Was the missing context completed?',
      summary: 'Record whether the blocker was resolved so related recommendations can be trusted or regenerated.',
      presets: ['Context completed', 'Partially completed', 'Still blocked'],
      measurementPlaceholder: 'profile readiness review',
      notePlaceholder: 'what context changed, what is still missing, whether to regenerate suggestions',
    };
  }
  if (type === 'plan_settings_update') {
    return {
      title: 'Did the plan change behave as expected?',
      summary: 'Compare the applied change against the preview and note whether the projected delta still feels useful.',
      presets: ['Applied as previewed', 'Applied with changes', 'Preview missed something'],
      measurementPlaceholder: 'plan tracking · scenario preview',
      notePlaceholder: 'preview matched, changed assumptions, follow-up needed',
    };
  }
  if (source.includes('portfolio_risk')) {
    return {
      title: 'What happened after the risk review?',
      summary: 'Record whether you rebalanced, redirected contributions, deferred, or rejected the concentration concern.',
      presets: ['Rebalanced', 'Redirected contributions', 'Deferred'],
      measurementPlaceholder: 'portfolio snapshot · manual review',
      notePlaceholder: 'allocation changed, decision deferred, risk accepted',
    };
  }
  if (source.includes('cash_liquidity')) {
    return {
      title: 'What changed after the liquidity review?',
      summary: 'Record whether cash moved, reserve targets changed, or profile assumptions were corrected.',
      presets: ['Cash moved', 'Target changed', 'Profile corrected'],
      measurementPlaceholder: 'cash review · profile update',
      notePlaceholder: 'reserve target, cash movement, corrected assumptions',
    };
  }
  return {
    title: 'How did it land?',
    summary: '',
    presets: ['Decision made', 'No action taken', 'Follow-up needed'],
    measurementPlaceholder: 'snapshot · plan tracking · manual',
    notePlaceholder: 'Context worth keeping.',
  };
}

function normalizeOutcomePreset(preset) {
  if (preset && typeof preset === 'object') {
    return {
      label: String(preset.label || '').trim(),
      code: String(preset.code || '').trim(),
      evidence: String(preset.evidence || '').trim(),
    };
  }
  return {
    label: String(preset || '').trim(),
    code: '',
    evidence: '',
  };
}

function renderPreview(preview) {
  if (!preview) return '';
  const rows = extractPreviewRows(preview);
  const warnings = preview.warnings || preview.simulation_delta?.warnings || [];
  if (!rows.length && !warnings.length) {
    return html`<p class="marginalia">No simulation delta returned for this preview.</p>`;
  }
  return html`
    ${rows.length ? html`
      <dl class="inline-preview-grid">
        ${raw(rows.map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`).join(''))}
      </dl>
    ` : ''}
    ${warnings.length ? html`
      <p class="inline-warning">${warnings.map(w => typeof w === 'string' ? w : (w?.message || '')).filter(Boolean).join(' · ')}</p>
    ` : ''}
  `;
}

function extractPreviewRows(preview) {
  if (!preview || typeof preview !== 'object') return [];
  const rows = [];
  const delta = preview.scenario_delta || preview.simulation_delta || preview;

  const candidates = [
    ['terminal value', delta.terminal_value_delta_usd ?? delta.future_value_delta_usd],
    ['retirement age', delta.retirement_age_delta],
    ['real value',     delta.real_value_delta_usd],
    ['savings rate',   delta.savings_rate_delta_pct],
  ];
  for (const [label, raw] of candidates) {
    if (raw == null) continue;
    const num = Number(raw);
    if (!Number.isFinite(num)) continue;
    if (label === 'retirement age') {
      rows.push([label, `${num >= 0 ? '+' : ''}${num.toFixed(1)} yr`]);
    } else if (label === 'savings rate') {
      rows.push([label, `${num >= 0 ? '+' : ''}${num.toFixed(1)}%`]);
    } else {
      rows.push([label, fmtUsdSigned(num)]);
    }
  }
  return rows;
}

function toLocalDatetime(d) {
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
