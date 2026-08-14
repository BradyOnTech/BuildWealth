// SETUP · flow chrome — the bar and the footer.
//
// Between them these own everything that is not the question itself: the bar
// carries the journey's only progress indicator, the footer the only navigation.
// Production duplicated progress across a stepper and a "0/5 steps finished"
// aside, and scattered navigation through the stage bodies.

import { html, raw } from '../../lib/dom.js';

// Per-step primary labels. Keeping them specific ("Continue to what I own")
// tells you where the button goes; a generic "Continue" does not.
const NEXT_LABELS = {
  welcome: 'Start with my household',
  foundation: 'Continue to what I own',
  portfolio: 'Continue to what is ahead',
  future: 'Show my first picture',
};

export function renderFlowBar(journey, active, busy) {
  const deferred = journey.filter(step => step.skipped).length;
  return html`
    <header class="setup-bar">
      <a class="setup-wordmark" href="#today">B<i>&amp;</i>W</a>
      <nav class="setup-progress" aria-label="Setup progress">
        ${raw(journey.map(step => {
          const state = step.completed ? 'complete' : step.skipped ? 'skipped' : step.current ? 'current' : 'upcoming';
          const reachable = step.completed || step.skipped || step.current || step.index < active.index;
          return html`
            <button type="button" class="setup-progress-step ${state}"
                    data-setup-step="${step.id}" ${busy || !reachable ? 'disabled' : ''}
                    aria-current="${step.current ? 'step' : 'false'}">
              <span class="setup-progress-track" aria-hidden="true"></span>
              <span class="setup-progress-label">${step.short}</span>
              <span class="setup-progress-state">${step.completed ? 'Done' : step.skipped ? 'Later' : step.current ? 'Now' : ''}</span>
            </button>
          `;
        }).join(''))}
      </nav>
      <div class="setup-bar-right">
        ${deferred ? html`<span class="setup-deferred">${deferred} left for later</span>` : ''}
        <a class="setup-leave" href="#today">Save &amp; exit <span aria-hidden="true">↗</span></a>
      </div>
    </header>
  `;
}

// The primary action still reflects whether the evidence exists: a step whose
// data is missing offers "leave this for later" rather than a Continue that
// would imply the step was satisfied.
export function renderFlowFoot(journey, active, busy) {
  const previous = journey[active.index - 1];
  const next = journey[active.index + 1];
  const last = !next;
  return html`
    <footer class="setup-foot">
      ${previous ? html`
        <button class="btn btn-quiet" type="button" data-setup-back="${previous.id}" ${busy ? 'disabled' : ''}>
          <span aria-hidden="true">←</span> Back
        </button>
      ` : ''}
      ${last ? html`
        <button class="btn btn-primary setup-next" type="button" data-setup-finish ${busy ? 'disabled' : ''}>
          Finish Setup and open Today <span aria-hidden="true">→</span>
        </button>
      ` : active.evidenceReady ? html`
        <button class="btn btn-primary setup-next" type="button"
                data-setup-next="${next.id}" data-setup-current="${active.id}" ${busy ? 'disabled' : ''}>
          ${NEXT_LABELS[active.id] || 'Continue'} <span aria-hidden="true">→</span>
        </button>
      ` : html`
        <button class="link-editorial setup-later" type="button"
                data-setup-skip="${next.id}" data-setup-current="${active.id}" ${busy ? 'disabled' : ''}>
          Leave this for later
        </button>
      `}
      <p class="setup-foot-note">${footNote(active)}</p>
    </footer>
  `;
}

function footNote(active) {
  if (active.id === 'welcome') return 'Usually 5–10 minutes for a useful first picture.';
  if (active.id === 'first_picture') return 'Every answer stays editable in Profile afterwards.';
  return active.evidenceReady
    ? 'This step has the evidence it needs.'
    : 'Skipping never marks this data complete — BuildWealth checks the evidence separately.';
}
