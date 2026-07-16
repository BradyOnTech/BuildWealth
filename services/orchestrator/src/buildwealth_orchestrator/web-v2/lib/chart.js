// Chart primitives — dependency-free SVG builders for the Almanac.
// Pure functions: data in, markup string out. Visual style lives in styles/charts.css.

import { esc } from './dom.js';

const FAN_MARGIN = { top: 14, right: 18, bottom: 30, left: 62 };

export function compactUsd(value) {
  if (value == null || value === '') return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (abs >= 1e9) return `${sign}$${trimTo(abs / 1e9)}B`;
  if (abs >= 1e6) return `${sign}$${trimTo(abs / 1e6)}M`;
  if (abs >= 1e3) return `${sign}$${trimTo(abs / 1e3)}k`;
  return `${sign}$${Math.round(abs)}`;
}

function trimTo(value) {
  const rounded = value >= 100 ? Math.round(value) : Math.round(value * 10) / 10;
  return String(rounded);
}

export function linearScale([d0, d1], [r0, r1]) {
  const span = d1 - d0;
  if (!Number.isFinite(span) || span === 0) return () => (r0 + r1) / 2;
  return value => r0 + ((value - d0) / span) * (r1 - r0);
}

// Round-numbered axis ticks covering [min, max].
export function niceTicks(min, max, count = 4) {
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return [];
  const rawStep = (max - min) / Math.max(1, count);
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const residual = rawStep / magnitude;
  const step = (residual >= 5 ? 10 : residual >= 2 ? 5 : residual >= 1 ? 2 : 1) * magnitude;
  const ticks = [];
  for (let tick = Math.ceil(min / step) * step; tick <= max + step * 1e-6; tick += step) {
    ticks.push(Math.round(tick * 1e6) / 1e6);
  }
  return ticks;
}

export function linePath(points) {
  const usable = points.filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));
  if (usable.length < 2) return '';
  return usable
    .map(([x, y], index) => `${index === 0 ? 'M' : 'L'}${rnd(x)},${rnd(y)}`)
    .join('');
}

// Closed region between an upper and lower series (same x order).
export function bandPath(upper, lower) {
  const top = linePath(upper);
  if (!top) return '';
  const bottom = lower
    .filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y))
    .reverse()
    .map(([x, y]) => `L${rnd(x)},${rnd(y)}`)
    .join('');
  return bottom ? `${top}${bottom}Z` : '';
}

function rnd(value) {
  return Math.round(value * 10) / 10;
}

// Percentile fan: layered bands (outermost first), overlay lines, x markers.
// rows: [{ [xKey], [band.lo], [band.hi], [line.key], ... }]
// seriesLabels: { seriesKey: display label } for the hover readout.
export function fanChart({
  rows = [],
  xKey = 'year',
  bands = [],
  lines = [],
  markers = [],
  guides = [],
  cloud = null,
  width = 720,
  height = 300,
  formatX = String,
  formatY = compactUsd,
  yTickCount = 4,
  ariaLabel = 'Chart',
  seriesLabels = {},
  hoverFormat = 'usd',
} = {}) {
  const usable = rows.filter(row => Number.isFinite(Number(row?.[xKey])));
  if (usable.length < 2) return '';
  const xValues = usable.map(row => Number(row[xKey]));
  const valueKeys = [
    ...bands.flatMap(band => [band.lo, band.hi]),
    ...lines.map(line => line.key),
  ];
  // Horizontal guides (reference values like "median net worth, ages 45–54")
  // join the y-domain so a guide is always visible when passed — callers
  // decide relevance so an outsized guide can't flatten the fan.
  const guideValues = guides.map(guide => Number(guide?.y)).filter(Number.isFinite);
  const yValues = usable
    .flatMap(row => valueKeys.map(key => Number(row[key])))
    .filter(Number.isFinite)
    .concat(guideValues);
  if (!yValues.length) return '';

  const plot = plotArea(width, height);
  const yMax = Math.max(...yValues);
  const yMin = Math.min(0, Math.min(...yValues));
  if (yMax <= yMin) return '';
  const x = linearScale([xValues[0], xValues[xValues.length - 1]], [plot.left, plot.right]);
  const y = linearScale([yMin, yMax * 1.04], [plot.bottom, plot.top]);

  // Path cloud: individual simulated trajectories drawn as faint strokes
  // beneath the percentile bands. cloud = { xs: [...], paths: [{ values, failed }] }.
  // Values are clamped to the band domain's ceiling so a runaway trial
  // thickens the top edge instead of flattening the fan.
  let cloudShapes = '';
  if (cloud && Array.isArray(cloud.paths) && Array.isArray(cloud.xs) && cloud.xs.length > 1) {
    const yCeil = yMax * 1.04;
    cloudShapes = cloud.paths
      .map(path => {
        const values = Array.isArray(path?.values) ? path.values : [];
        const points = cloud.xs
          .map((xValue, index) => {
            const value = Number(values[index]);
            return Number.isFinite(value) && Number.isFinite(Number(xValue))
              ? [x(Number(xValue)), y(Math.min(value, yCeil))]
              : null;
          })
          .filter(Boolean);
        const d = linePath(points);
        return d
          ? `<path class="chart-cloud-path${path.failed ? ' chart-cloud-path-failed' : ''}" d="${d}"></path>`
          : '';
      })
      .join('');
  }

  const bandShapes = bands
    .map(band => {
      const upper = seriesPoints(usable, xKey, band.hi, x, y);
      const lower = seriesPoints(usable, xKey, band.lo, x, y);
      const d = bandPath(upper, lower);
      return d ? `<path class="${esc(band.cls || 'chart-band-outer')}" d="${d}"></path>` : '';
    })
    .join('');
  const lineShapes = lines
    .map(line => {
      const d = linePath(seriesPoints(usable, xKey, line.key, x, y));
      return d ? `<path class="${esc(line.cls || 'chart-line-median')}" d="${d}"></path>` : '';
    })
    .join('');
  const markerShapes = markers
    .filter(marker => Number.isFinite(Number(marker?.x)))
    .filter(marker => Number(marker.x) >= xValues[0] && Number(marker.x) <= xValues[xValues.length - 1])
    .map((marker, index) => {
      const mx = rnd(x(Number(marker.x)));
      const cls = marker.cls ? ` ${esc(marker.cls)}` : '';
      // Stagger label rows so adjacent markers stay legible.
      const labelY = plot.top + 11 + (index % 2) * 14;
      const label = marker.label
        ? `<text class="chart-marker-label${cls}" x="${mx + 5}" y="${labelY}">${esc(marker.label)}</text>`
        : '';
      return `<line class="chart-marker${cls}" x1="${mx}" y1="${plot.top}" x2="${mx}" y2="${plot.bottom}"></line>${label}`;
    })
    .join('');
  const guideShapes = guides
    .filter(guide => Number.isFinite(Number(guide?.y)))
    .map(guide => {
      const gy = rnd(y(Number(guide.y)));
      const cls = guide.cls ? ` ${esc(guide.cls)}` : '';
      const label = guide.label
        ? `<text class="chart-guide-label${cls}" x="${plot.right - 4}" y="${gy - 4}" text-anchor="end">${esc(guide.label)}</text>`
        : '';
      return `<line class="chart-guide${cls}" x1="${plot.left}" y1="${gy}" x2="${plot.right}" y2="${gy}"></line>${label}`;
    })
    .join('');

  // Hover keys in top-to-bottom visual order: band highs, lines, band lows.
  const hoverKeys = [...new Set([
    ...bands.map(band => band.hi),
    ...lines.map(line => line.key),
    ...bands.map(band => band.lo).reverse(),
  ])];

  return svgShell({
    width,
    height,
    ariaLabel,
    hover: hoverAttr({
      xKey,
      formatY: hoverFormat,
      plot,
      labels: hoverLabels(hoverKeys, seriesLabels),
      points: usable.map(row => hoverPoint(row, xKey, hoverKeys, x)),
    }),
    content: [
      yAxis({ ticks: niceTicks(yMin, yMax, yTickCount), y, plot, formatY }),
      xAxis({ values: xValues, x, plot, formatX }),
      guideShapes,
      cloudShapes,
      bandShapes,
      lineShapes,
      markerShapes,
    ].join(''),
  });
}

// Vertical bars over an ordinal x (one bar per row).
export function barChart({
  rows = [],
  xKey = 'year',
  yKey = 'count',
  width = 720,
  height = 180,
  formatX = String,
  formatY = String,
  yTickCount = 3,
  barCls = 'chart-bar',
  ariaLabel = 'Bar chart',
  seriesLabels = {},
  hoverFormat = 'usd',
} = {}) {
  const usable = rows.filter(row => Number.isFinite(Number(row?.[yKey])));
  if (!usable.length) return '';
  const plot = plotArea(width, height);
  const yMax = Math.max(...usable.map(row => Number(row[yKey])));
  if (yMax <= 0) return '';
  const y = linearScale([0, yMax * 1.08], [plot.bottom, plot.top]);
  const slot = (plot.right - plot.left) / usable.length;
  const barWidth = Math.max(2, Math.min(28, slot * 0.62));

  const barShapes = usable
    .map((row, index) => {
      const value = Number(row[yKey]);
      const cx = plot.left + slot * (index + 0.5);
      const top = y(value);
      return `<rect class="${esc(barCls)}" x="${rnd(cx - barWidth / 2)}" y="${rnd(top)}" width="${rnd(barWidth)}" height="${rnd(plot.bottom - top)}"></rect>`;
    })
    .join('');
  const labelStep = Math.max(1, Math.ceil(usable.length / 8));
  const barLabels = usable
    .map((row, index) => {
      if (index % labelStep !== 0 && index !== usable.length - 1) return '';
      const cx = plot.left + slot * (index + 0.5);
      return `<text class="chart-axis-label" text-anchor="middle" x="${rnd(cx)}" y="${plot.bottom + 16}">${esc(formatX(row[xKey]))}</text>`;
    })
    .join('');

  return svgShell({
    width,
    height,
    ariaLabel,
    hover: hoverAttr({
      xKey,
      formatY: hoverFormat,
      plot,
      labels: hoverLabels([yKey], seriesLabels),
      // Bars are ordinal: px is the slot center, not a linear scale of x.
      points: usable.map((row, index) => ({
        x: row[xKey],
        px: rnd(plot.left + slot * (index + 0.5)),
        values: { [yKey]: roundHover(Number(row[yKey])) },
      })),
    }),
    content: [
      yAxis({ ticks: niceTicks(0, yMax, yTickCount), y, plot, formatY }),
      barShapes,
      barLabels,
    ].join(''),
  });
}

/* ── Hover payload ──
   Compact JSON that lib/chart_hover.js reads back off the DOM to drive the
   crosshair readout. Each point carries its viewBox x (px) so hover code
   never re-derives scales; values are rounded to keep the attribute small. */

export function hoverAttr({ xKey, formatY, plot, labels, points }) {
  if (!points.length) return '';
  const payload = { xKey, formatY, plot: { t: plot.top, b: plot.bottom }, labels, points };
  return ` data-chart-hover="${esc(JSON.stringify(payload))}"`;
}

export function hoverLabels(keys, seriesLabels = {}) {
  const labels = {};
  for (const key of keys) labels[key] = seriesLabels[key] || defaultSeriesLabel(key);
  return labels;
}

function hoverPoint(row, xKey, keys, x) {
  const values = {};
  for (const key of keys) {
    const value = Number(row[key]);
    if (Number.isFinite(value)) values[key] = roundHover(value);
  }
  const dataX = Number(row[xKey]);
  return { x: dataX, px: rnd(x(dataX)), values };
}

// P10/P90-style labels from percentile column names; fall back to the key.
function defaultSeriesLabel(key) {
  const match = /^(?:base_)?p(\d{1,2})_/.exec(key);
  if (match) return match[1] === '50' ? 'Median' : `P${match[1]}`;
  return String(key).replace(/_usd$/, '').replace(/_/g, ' ');
}

export function roundHover(value) {
  return Math.round(value * 100) / 100;
}

export function plotArea(width, height) {
  return {
    top: FAN_MARGIN.top,
    right: width - FAN_MARGIN.right,
    bottom: height - FAN_MARGIN.bottom,
    left: FAN_MARGIN.left,
  };
}

export function seriesPoints(rows, xKey, yKey, x, y) {
  return rows
    .map(row => {
      const value = Number(row[yKey]);
      return Number.isFinite(value) ? [x(Number(row[xKey])), y(value)] : null;
    })
    .filter(Boolean);
}

export function yAxis({ ticks, y, plot, formatY }) {
  return ticks
    .map(tick => {
      const ty = rnd(y(tick));
      return (
        `<line class="chart-grid" x1="${plot.left}" y1="${ty}" x2="${plot.right}" y2="${ty}"></line>` +
        `<text class="chart-axis-label" text-anchor="end" x="${plot.left - 8}" y="${ty + 3}">${esc(formatY(tick))}</text>`
      );
    })
    .join('');
}

export function xAxis({ values, x, plot, formatX }) {
  const step = Math.max(1, Math.ceil(values.length / 6));
  const last = values[values.length - 1];
  const picked = values
    .filter((_, index) => index % step === 0 || index === values.length - 1)
    .filter((value, index, list) =>
      index === list.length - 1 || Math.abs(x(value) - x(last)) >= 44);
  return (
    `<line class="chart-grid chart-baseline" x1="${plot.left}" y1="${plot.bottom}" x2="${plot.right}" y2="${plot.bottom}"></line>` +
    picked
      .map(value => `<text class="chart-axis-label" text-anchor="middle" x="${rnd(x(value))}" y="${plot.bottom + 16}">${esc(formatX(value))}</text>`)
      .join('')
  );
}

export function svgShell({ width, height, ariaLabel, content, hover = '' }) {
  return (
    `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(ariaLabel)}" preserveAspectRatio="xMidYMid meet"${hover}>` +
    `<title>${esc(ariaLabel)}</title>${content}</svg>`
  );
}
