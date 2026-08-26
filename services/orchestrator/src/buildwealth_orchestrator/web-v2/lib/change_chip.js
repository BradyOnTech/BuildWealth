// Change chips — no naked numbers.
// Every movement figure carries its delta, percent, and the honest window it
// was measured over ("past 31 days · portfolio"), so a number on the page
// never floats free of its basis. Inspired by Monarch's change chips, voiced
// in the Almanac's editorial idiom.

import { html } from './dom.js';
import { fmtUsdSigned, fmtPctSigned } from './format.js';

const ARROWS = { up: '↑', down: '↓', flat: '·' };

export function chipDirection(deltaUsd, deltaPct) {
  const usd = Number(deltaUsd);
  const pct = Number(deltaPct);
  const magnitude = Number.isFinite(usd) ? usd : (Number.isFinite(pct) ? pct : 0);
  if (magnitude > 0) return 'up';
  if (magnitude < 0) return 'down';
  return 'flat';
}

// Name the window the delta was actually measured over — never imply a
// calendar month the snapshots may not cover.
export function windowLabel(days) {
  const d = Number(days);
  if (!Number.isFinite(d) || d <= 0) return '';
  if (d <= 1) return 'past day';
  if (d < 13) return `past ${Math.round(d)} days`;
  if (d < 25) {
    const weeks = Math.round(d / 7);
    return weeks <= 1 ? 'past week' : `past ${weeks} weeks`;
  }
  if (d < 45) return 'past month';
  if (d < 320) return `past ${Math.round(d / 30.4)} months`;
  if (d < 500) return 'past year';
  return `past ${Math.round(d / 365.25)} years`;
}

// changeChip({ deltaUsd, deltaPct, windowDays, basis })
// Renders "↑ +$15,000 (+5.2%) · past month · portfolio" as an inline chip.
// Returns '' when there is no real delta to show — the Almanac never
// fabricates movement.
export function changeChip({ deltaUsd = null, deltaPct = null, windowDays = null, basis = '' } = {}) {
  if (deltaUsd == null) return '';
  const usd = Number(deltaUsd);
  if (!Number.isFinite(usd)) return '';
  const pct = Number(deltaPct);
  const direction = chipDirection(usd, Number.isFinite(pct) ? pct : null);
  const window = windowLabel(windowDays);
  const label = [window, basis].filter(Boolean).join(' · ');

  return html`
    <span class="change-chip delta-${direction}">
      <span class="chip-arrow" aria-hidden="true">${ARROWS[direction]}</span>
      <b class="num-mono">${fmtUsdSigned(usd)}${Number.isFinite(pct) ? html` (${fmtPctSigned(pct)})` : ''}</b>
      ${label ? html`<span class="chip-label"> ${label}</span>` : ''}
    </span>
  `;
}
