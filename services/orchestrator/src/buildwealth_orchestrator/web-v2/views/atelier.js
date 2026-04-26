// ATELIER — placeholder for the foundation/admin shelf.
// Collapses profile, sync, import, research, workflows, and settings.

export const meta = {
  id: 'atelier',
  label: 'Atelier',
  numeral: 'V',
  group: 'studio',
};

export function template() {
  return `
    <section class="page">
      <div class="placeholder">
        <span class="glyph">⁂</span>
        <h2>The Atelier.</h2>
        <p>
          Foundation work — financial profile, broker sync, statement
          import, research, workflows and settings — is being gathered
          into one quiet shelf so the daily surfaces stay daily.
          Use the classic views below until the move is complete.
        </p>
        <p class="marginalia">Profile · Sync &amp; Import · Research · Workflows · Settings</p>
        <div class="entry-meta">
          <a class="link-editorial" href="/#profile">Profile</a>
          <a class="link-editorial" href="/#sync">Sync &amp; Import</a>
          <a class="link-editorial" href="/#research">Research</a>
          <a class="link-editorial" href="/#workflows">Workflows</a>
          <a class="link-editorial" href="/#settings">Settings</a>
        </div>
      </div>
    </section>
  `;
}

export function init() { /* no-op */ }
