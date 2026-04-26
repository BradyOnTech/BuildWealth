// PORTFOLIO — three movements.
//   I.   The standing       — total value + performance
//   II.  The composition    — allocation strata + top holdings
//   III. The watch          — risk alerts or all-clear
// Footer — Look closer (links to classic surfaces for actions not yet rebuilt).

import { api } from '../lib/api.js';
import { state } from '../lib/state.js';
import { html, raw, $, setView } from '../lib/dom.js';
import { renderStanding } from './portfolio/standing.js';
import { renderComposition } from './portfolio/composition.js';
import { renderWatch } from './portfolio/watch.js';

export const meta = {
  id: 'portfolio',
  label: 'Portfolio',
  numeral: 'II',
  group: 'daily',
};

export function template() {
  return html`
    <section class="page" id="portfolio-page">
      ${raw(skeletonHero())}
      ${raw(skeletonSection('II', 'The composition'))}
      ${raw(skeletonSection('III', 'The watch'))}
    </section>
  `;
}

export async function init() {
  const root = $('#portfolio-page');
  if (!root) return;
  let data = null;
  try {
    data = await api.holdings();
    state.portfolio = data;
  } catch (err) {
    setView(root, html`
      <p class="hero-eyebrow">Portfolio</p>
      <p class="error-banner">${err.message}</p>
    `);
    return;
  }

  setView(root, html`
    ${raw(renderStanding(data))}
    ${raw(renderComposition(data))}
    ${raw(renderWatch(data))}
    ${raw(renderLookCloser())}
  `);
}

function renderLookCloser() {
  return html`
    <footer class="look-closer">
      <span class="section-eyebrow">Look closer</span>
      <div class="look-closer-row">
        <a class="link-editorial" href="/#portfolio">Full holdings table</a>
        <a class="link-editorial" href="/#portfolio">Record a transaction</a>
        <a class="link-editorial" href="/#portfolio">Backfill history</a>
        <a class="link-editorial" href="/#portfolio">Watchlist</a>
        <a class="link-editorial" href="/#portfolio">Risk thresholds</a>
      </div>
      <p class="look-closer-note">Each opens the classic surface — these views haven't been re-set in the new vocabulary yet.</p>
    </footer>
  `;
}

function skeletonHero() {
  return html`
    <section class="hero-stack">
      <span class="hero-eyebrow skeleton" style="width: 280px;">.</span>
      <h1 class="hero-number skeleton" style="width: 60%; height: var(--t-hero);">.</h1>
      <p class="hero-marginalia skeleton" style="width: 480px;">.</p>
    </section>
  `;
}

function skeletonSection(numeral, title) {
  return html`
    <section>
      <header class="section-head">
        <span class="section-eyebrow">Movement ${numeral}</span>
        <h2 class="section-title">${title}</h2>
      </header>
      <div class="skeleton" style="height: 120px;">.</div>
    </section>
  `;
}
