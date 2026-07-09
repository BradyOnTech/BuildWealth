// Composer — multi-line textarea with auto-grow and ⌘+Enter submit.
// Stateless renderer; the parent orchestrator wires events via delegation.

import { html } from '../../lib/dom.js';

export function renderComposer({ busy = false, draft = '', useLive = false } = {}) {
  return html`
    <form class="composer" id="composer" autocomplete="off">
      <div class="composer-inner">
        <div class="composer-card">
          <textarea
            class="composer-textarea"
            id="composer-textarea"
            name="question"
            placeholder="Message Copilot…"
            rows="1"
            ${busy ? 'disabled' : ''}>${draft}</textarea>
          <div class="composer-row">
            <div class="composer-options">
              <label class="composer-option" title="Use a live portfolio snapshot">
                <input type="checkbox" id="composer-live" ${useLive ? 'checked' : ''} />
                Live
              </label>
              <span class="composer-hint">
                <kbd>${isMac() ? '⌘' : 'Ctrl'}</kbd><kbd>↵</kbd>
              </span>
            </div>
            <button type="submit" class="composer-send" id="composer-submit" ${busy ? 'disabled' : ''} title="Send">
              ${busy ? '…' : 'Send'}
            </button>
          </div>
        </div>
      </div>
    </form>
  `;
}

export function attachComposerBehavior(rootEl, { onSubmit }) {
  const textarea = rootEl.querySelector('#composer-textarea');
  const form     = rootEl.querySelector('#composer');
  if (!textarea || !form) return;

  // Focus + auto-grow.
  textarea.focus();
  autoGrow(textarea);
  textarea.addEventListener('input', () => autoGrow(textarea));

  textarea.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const value = textarea.value.trim();
    if (!value) return;
    const useLive = !!rootEl.querySelector('#composer-live')?.checked;
    onSubmit({ question: value, useLive });
  });
}

function autoGrow(textarea) {
  textarea.style.height = 'auto';
  const max = 200;
  textarea.style.height = `${Math.min(textarea.scrollHeight, max)}px`;
}

function isMac() {
  if (typeof navigator === 'undefined') return false;
  return /Mac|iPod|iPhone|iPad/.test(navigator.platform || '');
}
