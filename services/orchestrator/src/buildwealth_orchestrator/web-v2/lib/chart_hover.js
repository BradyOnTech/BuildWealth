// Hover readouts for SVG charts — vertical crosshair plus a floating value
// label near the cursor, fed by the data-chart-hover payload lib/chart.js
// embeds on each svg. One delegated listener at document level so the wiring
// survives innerHTML re-renders. Pure helpers are exported for tests; DOM
// binding is guarded so this module imports cleanly under node:test.

import { compactUsd } from './chart.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const HOVER_SELECTOR = 'svg.chart[data-chart-hover]';

// Nearest point by horizontal distance. Prefers viewBox px when present so
// ordinal charts (bars) resolve correctly; falls back to data x.
export function findNearestPoint(points, target) {
  if (!Array.isArray(points) || !Number.isFinite(Number(target))) return null;
  let best = null;
  let bestDistance = Infinity;
  for (const point of points) {
    const at = Number(point?.px ?? point?.x);
    if (!Number.isFinite(at)) continue;
    const distance = Math.abs(at - Number(target));
    if (distance < bestDistance) {
      best = point;
      bestDistance = distance;
    }
  }
  return best;
}

export function formatHoverValue(value, formatY = 'usd') {
  if (formatY === 'usd') return compactUsd(value);
  if (formatY === 'pct') return `${value}%`;
  return String(value);
}

const payloadCache = new WeakMap();
let crosshair = null;
let readout = null;
let raf = 0;
let lastEvent = null;

function payloadFor(svg) {
  if (payloadCache.has(svg)) return payloadCache.get(svg);
  let payload = null;
  try {
    payload = JSON.parse(svg.getAttribute('data-chart-hover') || 'null');
  } catch {
    payload = null;
  }
  if (!Array.isArray(payload?.points) || !payload.points.length) payload = null;
  payloadCache.set(svg, payload);
  return payload;
}

function track(svg, clientX, clientY) {
  const payload = payloadFor(svg);
  const rect = svg.getBoundingClientRect();
  const viewBox = svg.viewBox?.baseVal;
  if (!payload || !viewBox?.width || !rect.width) return clear();
  // preserveAspectRatio "meet" + height:auto keep scaling uniform, so a
  // simple width ratio maps client x into viewBox units.
  const vx = ((clientX - rect.left) / rect.width) * viewBox.width;
  const point = findNearestPoint(payload.points, vx);
  if (!point) return clear();
  drawCrosshair(svg, payload, point, viewBox);
  drawReadout(payload, point, clientX, clientY);
}

function drawCrosshair(svg, payload, point, viewBox) {
  // Re-renders replace the svg under us; drop any orphaned line first.
  if (crosshair && (crosshair.ownerSVGElement !== svg || !svg.contains(crosshair))) {
    crosshair.remove();
    crosshair = null;
  }
  if (!crosshair) {
    crosshair = document.createElementNS(SVG_NS, 'line');
    crosshair.setAttribute('class', 'chart-crosshair');
    svg.appendChild(crosshair);
  }
  const px = Number(point.px ?? point.x);
  crosshair.setAttribute('x1', px);
  crosshair.setAttribute('x2', px);
  crosshair.setAttribute('y1', payload.plot?.t ?? 0);
  crosshair.setAttribute('y2', payload.plot?.b ?? viewBox.height);
}

function drawReadout(payload, point, clientX, clientY) {
  if (!readout) {
    readout = document.createElement('div');
    readout.className = 'chart-hover-readout';
    document.body.appendChild(readout);
  }
  readout.textContent = '';
  const xLine = document.createElement('div');
  xLine.className = 'readout-x';
  xLine.textContent = String(point.x);
  readout.appendChild(xLine);
  for (const [key, label] of Object.entries(payload.labels || {})) {
    if (!(key in (point.values || {}))) continue;
    const row = document.createElement('div');
    row.className = 'readout-row';
    const name = document.createElement('span');
    name.textContent = label;
    const value = document.createElement('span');
    value.className = 'readout-val';
    value.textContent = formatHoverValue(point.values[key], payload.formatY);
    row.append(name, value);
    readout.appendChild(row);
  }
  readout.style.display = 'block';
  // Beside the cursor; flip when the box would clip a viewport edge.
  const pad = 14;
  let left = clientX + pad;
  let top = clientY + pad;
  const { offsetWidth: w, offsetHeight: h } = readout;
  if (left + w > window.innerWidth - 8) left = clientX - w - pad;
  if (top + h > window.innerHeight - 8) top = clientY - h - pad;
  readout.style.left = `${left}px`;
  readout.style.top = `${top}px`;
}

function clear() {
  if (crosshair) {
    crosshair.remove();
    crosshair = null;
  }
  if (readout) readout.style.display = 'none';
}

function onMouseMove(event) {
  lastEvent = event;
  if (raf) return;
  raf = requestAnimationFrame(() => {
    raf = 0;
    const target = lastEvent.target;
    const svg = target instanceof Element ? target.closest(HOVER_SELECTOR) : null;
    if (svg) track(svg, lastEvent.clientX, lastEvent.clientY);
    else clear();
  });
}

// Bind once, and only where hover exists — touch/keyboard flows never see
// these artifacts. Nothing animates, so prefers-reduced-motion needs no branch.
if (typeof document !== 'undefined'
  && !(typeof matchMedia === 'function' && matchMedia('(hover: none)').matches)) {
  document.addEventListener('mousemove', onMouseMove, { passive: true });
  document.addEventListener('mouseleave', clear);
}
