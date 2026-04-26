// COPILOT — placeholder. Chat + Inbox side rail planned for next iteration.

export const meta = {
  id: 'copilot',
  label: 'Copilot',
  numeral: 'IV',
  group: 'daily',
};

export function template() {
  return `
    <section class="page">
      <div class="placeholder">
        <span class="glyph">¶</span>
        <h2>Copilot is moving in next.</h2>
        <p>
          The chat surface and recommendation inbox will live together
          here — questions on the left, the day's three things on the
          right. The classic Copilot view remains available below.
        </p>
        <a class="link-editorial" href="/#copilot">Open in classic</a>
      </div>
    </section>
  `;
}

export function init() { /* no-op */ }
