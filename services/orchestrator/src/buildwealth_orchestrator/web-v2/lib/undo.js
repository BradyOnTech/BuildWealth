// Undo toast — one at a time, six seconds, keyboard reachable.
// showUndoToast({ message, onUndo }) renders a fixed toast; clicking Undo (or
// pressing its button via keyboard) runs onUndo and dismisses. A new toast
// replaces any live one. Pure DOM, no dependencies, safe under test (no-ops
// without a document).

const TOAST_MS = 6000;
let liveToast = null;
let liveTimer = null;

export function showUndoToast({ message, onUndo, actionLabel = 'Undo' } = {}) {
  if (typeof document === 'undefined') return null;
  dismissUndoToast();

  const toast = document.createElement('div');
  toast.className = 'undo-toast';
  toast.setAttribute('role', 'status');
  toast.setAttribute('aria-live', 'polite');

  const text = document.createElement('span');
  text.className = 'undo-toast-message';
  text.textContent = String(message || 'Done.');
  toast.appendChild(text);

  if (typeof onUndo === 'function') {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'undo-toast-action';
    button.textContent = actionLabel;
    button.addEventListener('click', async () => {
      dismissUndoToast();
      try { await onUndo(); } catch { /* restore errors surface via view state */ }
    });
    toast.appendChild(button);
  }

  document.body.appendChild(toast);
  liveToast = toast;
  liveTimer = setTimeout(dismissUndoToast, TOAST_MS);
  return toast;
}

export function dismissUndoToast() {
  if (liveTimer) { clearTimeout(liveTimer); liveTimer = null; }
  if (!liveToast) return;
  const toast = liveToast;
  liveToast = null;
  // Exit along the entrance path (down and away), faster than it arrived —
  // the system responding should never feel slower than the user acting.
  toast.classList.add('leaving');
  const remove = () => toast.remove();
  toast.addEventListener('transitionend', remove, { once: true });
  setTimeout(remove, 200); // fallback: reduced motion zeroes the transition
}
