// Profile · The life-plans interview.
// A few questions about the next chapter, answered in plain words, returned
// as draft dated goals to review before anything is saved. Dated goals are
// what the deployment engine protects as cash — this is where they come from.
//
// Flow: closed card → questions (timeframe pills + one number each) →
// drafts review (check, edit, apply) → goals land in the table below.
// "Not now" across the board offers to pause goal nudges instead of nagging.

import { api } from '../../lib/api.js';
import { html, raw, esc } from '../../lib/dom.js';
import { persist, render as renderProfile } from '../profile.js';

const st = {
  open: false,
  busy: false,
  error: null,
  interview: null,
  answers: {},        // question id → { timeframe, amount_usd, months, label }
  drafts: null,       // POST /api/life-plans/drafts payload
  dropped: new Set(), // draft indexes the user unchecked
  edits: {},          // draft index → { target_amount_usd, target_date }
  timelinePlan: null,          // active plan {id, title} when one exists
  timelineDropped: new Set(),  // draft indexes NOT marked on the timeline
  timelineAdded: 0,
  appliedCount: 0,
  pausedNudges: false,
};

export function renderLifeInterview(ui) {
  if (!st.open) return renderClosedCard(ui);
  if (st.drafts) return renderDraftReview();
  return renderQuestions();
}

function renderClosedCard(ui) {
  const datedGoals = (ui.profile?.goal_items || []).filter(g => g && g.target_date).length;
  const timelineNote = st.timelineAdded
    ? ` ${st.timelineAdded} marked on the Plan timeline — the trajectory now shows them.`
    : '';
  const note = st.appliedCount
    ? `${st.appliedCount} goal${st.appliedCount === 1 ? '' : 's'} added — the table below has them.${timelineNote}`
    : st.pausedNudges
      ? 'Goal nudges paused. Sit again whenever plans change.'
      : datedGoals
        ? `${datedGoals} dated goal${datedGoals === 1 ? '' : 's'} on file. Plans change — sit again anytime.`
        : 'Nothing dated yet. Five minutes here shapes how your cash is treated.';
  return html`
    <aside class="life-interview" data-life-interview>
      <header class="section-head compact">
        <span class="section-eyebrow">The interview</span>
        <h3 class="section-title">A few questions about the next chapter.</h3>
        <p class="section-lede">
          A home, children, a break, something big — dated goals claim cash
          before the Almanac suggests investing it. Answers become drafts you
          review; nothing is saved until you say so.
        </p>
      </header>
      <div class="entry-actions">
        <button class="action-link" data-interview-action="open">Sit for the interview <span class="arrow">›</span></button>
        <span class="marginalia">${esc(note)}</span>
      </div>
      ${st.error ? html`<p class="error-banner">${esc(st.error)}</p>` : ''}
    </aside>
  `;
}

function renderQuestions() {
  const interview = st.interview || {};
  const questions = Array.isArray(interview.questions) ? interview.questions : [];
  const timeframes = Array.isArray(interview.timeframes) ? interview.timeframes : [];
  const answered = questions.filter(q => st.answers[q.id]?.timeframe).length;
  return html`
    <aside class="life-interview open" data-life-interview>
      <header class="section-head compact">
        <span class="section-eyebrow">The interview</span>
        <h3 class="section-title">The next chapter, in ${questions.length} questions.</h3>
        <p class="section-lede">Rough guesses are welcome — the date matters more than the number, and everything stays editable.</p>
      </header>
      ${st.error ? html`<p class="error-banner">${esc(st.error)}</p>` : ''}
      <ol class="life-questions">
        ${raw(questions.map(q => renderQuestion(q, timeframes)).join(''))}
      </ol>
      <p class="marginalia">${esc(interview.not_asked || '')}</p>
      <div class="entry-actions">
        <button class="action-link" data-interview-action="draft" ${st.busy || !answered ? 'disabled' : ''}>
          ${st.busy ? 'Drafting…' : `Draft the goals (${answered} answered)`} <span class="arrow">›</span>
        </button>
        <button class="action-link muted" data-interview-action="close">Not now <span class="arrow">›</span></button>
      </div>
    </aside>
  `;
}

function renderQuestion(question, timeframes) {
  const answer = st.answers[question.id] || {};
  const covered = question.already_covered;
  const active = answer.timeframe && answer.timeframe !== 'not_now';
  return html`
    <li class="life-question" data-life-question="${esc(question.id)}">
      <p class="life-question-prompt">${esc(question.prompt)}</p>
      <p class="marginalia">${esc(question.why)}</p>
      ${covered ? html`
        <p class="life-question-covered">Already written down: <strong>${esc(covered.label)}</strong> — answer again only if there's more.</p>
      ` : ''}
      <div class="life-timeframes">
        ${raw(timeframes.map(tf => html`
          <label class="life-timeframe ${answer.timeframe === tf.id ? 'selected' : ''}">
            <input type="radio" name="life-${esc(question.id)}" value="${esc(tf.id)}"
                   data-interview-field="timeframe" data-question-id="${esc(question.id)}"
                   ${answer.timeframe === tf.id ? 'checked' : ''}>
            ${esc(tf.label)}
          </label>
        `).join(''))}
      </div>
      ${active ? html`
        <div class="life-amount-row">
          <label class="life-amount">
            <span class="assumption-label">${esc(question.amount_label)}</span>
            <input type="number" min="0" step="100" inputmode="decimal"
                   value="${esc(answer.amount_usd ?? question.amount_default_usd ?? '')}"
                   data-interview-field="amount_usd"
                   data-question-id="${esc(question.id)}">
          </label>
          ${question.id === 'big_purchase' ? html`
            <label class="life-amount">
              <span class="assumption-label">What is it?</span>
              <input type="text" maxlength="60" placeholder="Car, move, the trip…"
                     value="${esc(answer.label ?? '')}"
                     data-interview-field="label" data-question-id="big_purchase">
            </label>
          ` : ''}
          <span class="marginalia">${esc(question.amount_hint || '')}</span>
        </div>
      ` : ''}
    </li>
  `;
}

function renderDraftReview() {
  const drafts = Array.isArray(st.drafts?.drafts) ? st.drafts.drafts : [];
  const kept = drafts.filter((_, index) => !st.dropped.has(index)).length;
  if (st.drafts?.no_plans) {
    return html`
      <aside class="life-interview open" data-life-interview>
        <header class="section-head compact">
          <span class="section-eyebrow">The interview</span>
          <h3 class="section-title">Nothing on the horizon — noted.</h3>
          <p class="section-lede">${esc(st.drafts.no_plans_hint || '')}</p>
        </header>
        ${st.error ? html`<p class="error-banner">${esc(st.error)}</p>` : ''}
        <div class="entry-actions">
          <button class="action-link" data-interview-action="pause-nudges" ${st.busy ? 'disabled' : ''}>
            ${st.busy ? 'Saving…' : 'Pause goal nudges'} <span class="arrow">›</span>
          </button>
          <button class="action-link muted" data-interview-action="back">Back to the questions <span class="arrow">›</span></button>
        </div>
      </aside>
    `;
  }
  return html`
    <aside class="life-interview open" data-life-interview>
      <header class="section-head compact">
        <span class="section-eyebrow">The interview · drafts</span>
        <h3 class="section-title">${drafts.length} draft${drafts.length === 1 ? '' : 's'} — yours to edit.</h3>
        <p class="section-lede">Starting points, not verdicts. Uncheck what doesn't fit, adjust the numbers, then add the rest.</p>
      </header>
      ${st.error ? html`<p class="error-banner">${esc(st.error)}</p>` : ''}
      <ol class="life-drafts">
        ${raw(drafts.map((draft, index) => renderDraft(draft, index)).join(''))}
      </ol>
      <div class="entry-actions">
        <button class="action-link" data-interview-action="apply" ${st.busy || !kept ? 'disabled' : ''}>
          ${st.busy ? 'Adding…' : `Add ${kept} goal${kept === 1 ? '' : 's'} to the profile`} <span class="arrow">›</span>
        </button>
        <button class="action-link muted" data-interview-action="back">Back to the questions <span class="arrow">›</span></button>
      </div>
    </aside>
  `;
}

function renderDraft(draft, index) {
  const edit = st.edits[index] || {};
  const amount = edit.target_amount_usd ?? draft.target_amount_usd;
  const date = edit.target_date ?? draft.target_date;
  const kept = !st.dropped.has(index);
  const timelineEligible = Boolean(st.timelinePlan && draft.timeline_event);
  const onTimeline = timelineEligible && !st.timelineDropped.has(index);
  return html`
    <li class="life-draft ${kept ? '' : 'dropped'}">
      <label class="life-draft-keep">
        <input type="checkbox" data-draft-pick="${index}" ${kept ? 'checked' : ''}>
        <strong>${esc(draft.label)}</strong>
        <span class="life-draft-priority">${esc(draft.priority)}</span>
      </label>
      <div class="life-draft-fields">
        <label class="life-amount">
          <span class="assumption-label">Target</span>
          <input type="number" min="0" step="500" value="${esc(amount)}"
                 data-draft-field="target_amount_usd" data-draft-index="${index}">
        </label>
        <label class="life-amount">
          <span class="assumption-label">By</span>
          <input type="date" value="${esc(date)}"
                 data-draft-field="target_date" data-draft-index="${index}">
        </label>
      </div>
      ${timelineEligible ? html`
        <label class="life-draft-timeline">
          <input type="checkbox" data-draft-timeline="${index}" ${onTimeline ? 'checked' : ''} ${kept ? '' : 'disabled'}>
          ${draft.timeline_event.recurring_frequency === 'monthly' ? html`
            Also mark on the “${esc(st.timelinePlan.title || 'Plan')}” timeline — the trajectory
            will model income stepping down from ${esc(String(date || '').slice(0, 4))} on.
          ` : html`
            Also mark on the “${esc(st.timelinePlan.title || 'Plan')}” timeline — the trajectory
            will model this money leaving in ${esc(String(date || '').slice(0, 4))}.
          `}
        </label>
        <a class="link-editorial life-draft-preview" href="${previewBranchHref(draft, index)}">
          Preview first in What-ifs — run it as a simulation, save nothing <span class="arrow">›</span>
        </a>
      ` : ''}
      <p class="marginalia">${esc(draft.sentence)}</p>
    </li>
  `;
}

// Deep link into Plan → What-ifs with this draft's event as an ephemeral
// branch template: forecast without committing anything to the timeline.
function previewBranchHref(draft, index) {
  const edit = st.edits[index] || {};
  const event = draft.timeline_event || {};
  const params = new URLSearchParams();
  if (st.timelinePlan?.id) params.set('id', st.timelinePlan.id);
  params.set('section', 'branches');
  params.set('pv_label', String(draft.label || 'Life event'));
  params.set('pv_date', String(edit.target_date ?? event.date ?? ''));
  params.set('pv_type', String(event.event_type || 'milestone'));
  if (event.impact_type) params.set('pv_impact', String(event.impact_type));
  params.set('pv_amount', String(event.amount_usd ?? 0));
  params.set('pv_freq', String(event.recurring_frequency || 'one_time'));
  return `#plan?${params.toString()}`;
}

/* ─────────────  Events (routed from profile.js)  ───────────── */

export async function onInterviewAction(ui, action) {
  st.error = null;
  if (action === 'open') {
    st.open = true;
    st.drafts = null;
    if (!st.interview) {
      st.busy = true;
      renderProfile();
      try {
        st.interview = await api.lifeInterview();
        // Questions already covered by a recorded goal default to "not now".
        for (const question of st.interview.questions || []) {
          if (question.already_covered && !st.answers[question.id]) {
            st.answers[question.id] = { timeframe: 'not_now' };
          }
        }
      } catch (err) {
        st.error = err.message;
        st.open = false;
      }
      st.busy = false;
    }
    renderProfile();
    return;
  }
  if (action === 'close') { st.open = false; renderProfile(); return; }
  if (action === 'back') { st.drafts = null; st.dropped = new Set(); st.edits = {}; renderProfile(); return; }
  if (action === 'draft') return draftGoals();
  if (action === 'apply') return applyDrafts(ui);
  if (action === 'pause-nudges') return pauseNudges(ui);
}

export function onInterviewField(el) {
  const questionId = String(el.dataset.questionId || '');
  const field = String(el.dataset.interviewField || '');
  if (!questionId || !field) return;
  st.answers[questionId] = { ...(st.answers[questionId] || {}), [field]: el.value };
  // Only timeframe changes reshape the row (amount inputs appear/disappear);
  // re-rendering on amount keystrokes would eat focus and digits.
  if (field === 'timeframe') renderProfile();
}

export function onDraftPick(el) {
  const index = Number(el.dataset.draftPick);
  if (!Number.isInteger(index)) return;
  if (el.checked) st.dropped.delete(index);
  else st.dropped.add(index);
  renderProfile();
}

export function onDraftTimeline(el) {
  const index = Number(el.dataset.draftTimeline);
  if (!Number.isInteger(index)) return;
  if (el.checked) st.timelineDropped.delete(index);
  else st.timelineDropped.add(index);
}

export function onDraftField(el) {
  const index = Number(el.dataset.draftIndex);
  const field = String(el.dataset.draftField || '');
  if (!Number.isInteger(index) || !field) return;
  st.edits[index] = { ...(st.edits[index] || {}), [field]: el.value };
}

async function draftGoals() {
  st.busy = true;
  renderProfile();
  try {
    st.drafts = await api.lifePlanDrafts(st.answers);
    st.dropped = new Set();
    st.edits = {};
    st.timelineDropped = new Set();
    st.timelinePlan = await resolveActivePlan();
  } catch (err) {
    st.error = err.message;
  }
  st.busy = false;
  renderProfile();
}

// The timeline bridge needs a plan to write to; without one the drafts
// review simply doesn't offer it.
async function resolveActivePlan() {
  try {
    const payload = await api.plans();
    const plans = Array.isArray(payload?.plans) ? payload.plans : (Array.isArray(payload) ? payload : []);
    const active = plans.find(plan => plan && plan.is_active) || plans[0] || null;
    return active ? { id: String(active.id || ''), title: String(active.title || 'Plan') } : null;
  } catch {
    return null;
  }
}

async function applyDrafts(ui) {
  const drafts = Array.isArray(st.drafts?.drafts) ? st.drafts.drafts : [];
  const goals = drafts
    .filter((_, index) => !st.dropped.has(index))
    .map((draft, position) => {
      const index = drafts.indexOf(draft);
      const edit = st.edits[index] || {};
      const amount = Number(edit.target_amount_usd ?? draft.target_amount_usd);
      return {
        id: uid(),
        label: String(draft.label || `Goal ${position + 1}`),
        target_amount_usd: Number.isFinite(amount) && amount > 0 ? amount : draft.target_amount_usd,
        target_date: String(edit.target_date ?? draft.target_date ?? '') || null,
        priority: draft.priority || 'medium',
        notes: draft.notes || '',
      };
    });
  if (!goals.length || !ui.profile) return;
  st.busy = true;
  renderProfile();
  const goalsBefore = ui.profile.goal_items || [];
  ui.profile.goal_items = [...goalsBefore, ...goals];
  const saved = await persist({ optimistic: false });
  st.busy = false;
  if (!saved) {
    // Roll back the optimistic push: a table showing unsaved goals is a lie.
    ui.profile.goal_items = goalsBefore;
    st.error = 'The goals could not be saved — nothing was added. Try again.';
    renderProfile();
    return;
  }
  st.appliedCount = goals.length;
  st.timelineAdded = await appendTimelineEvents(drafts);
  st.open = false;
  st.drafts = null;
  st.answers = {};
  st.interview = null; // Reload next time: covered-detection must see the new goals.
  renderProfile();
}

// Goals saved — now the timeline twins. A failure here must not undo the
// goals; it reports separately and leaves the timeline untouched.
async function appendTimelineEvents(drafts) {
  const planId = st.timelinePlan?.id;
  if (!planId) return 0;
  const events = drafts
    .map((draft, index) => ({ draft, index }))
    .filter(({ draft, index }) =>
      !st.dropped.has(index) && !st.timelineDropped.has(index) && draft.timeline_event)
    .map(({ draft, index }) => {
      const edit = st.edits[index] || {};
      const twin = draft.timeline_event;
      // Amount edits apply only to one-time twins, where the goal target IS
      // the event amount. A recurring income bend is a monthly figure the
      // goal-target edit doesn't describe.
      const editable = twin.recurring_frequency === 'one_time' && Number(twin.amount_usd) > 0;
      const amount = Number(edit.target_amount_usd ?? twin.amount_usd);
      return {
        ...twin,
        date: String(edit.target_date ?? twin.date ?? ''),
        amount_usd: editable && Number.isFinite(amount) && amount > 0 ? amount : twin.amount_usd,
      };
    })
    .filter(event => event.date);
  if (!events.length) return 0;
  try {
    const current = await api.planTimeline(planId);
    await api.updatePlanTimeline(planId, {
      events: [...(Array.isArray(current?.events) ? current.events : []), ...events],
      retirement: current?.retirement || {},
    });
    return events.length;
  } catch (err) {
    st.error = `Goals saved, but the Plan timeline could not be updated: ${err.message}`;
    return 0;
  }
}

async function pauseNudges(ui) {
  if (!ui.profile) return;
  st.busy = true;
  renderProfile();
  const flagsBefore = ui.profile.flags || {};
  ui.profile.flags = { ...flagsBefore, no_goals: true };
  const saved = await persist({ optimistic: false });
  st.busy = false;
  if (!saved) {
    ui.profile.flags = flagsBefore;
    st.error = 'Could not save the preference — nudges are unchanged.';
    renderProfile();
    return;
  }
  st.pausedNudges = true;
  st.open = false;
  st.drafts = null;
  renderProfile();
}

function uid() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return `id-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`;
}
