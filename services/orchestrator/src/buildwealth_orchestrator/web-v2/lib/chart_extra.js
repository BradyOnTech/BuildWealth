// Distribution + composition chart primitives for the Simulation Studio.
// Same contract as lib/chart.js: pure string builders, styled in charts.css.

import { esc } from './dom.js';
import {
  compactUsd,
  linearScale,
  niceTicks,
  linePath,
  bandPath,
  plotArea,
  svgShell,
  hoverAttr,
  hoverLabels,
  roundHover,
  yAxis,
} from './chart.js';

function rnd(value) {
  return Math.round(value * 10) / 10;
}

// Histogram over pre-binned data (server-side bins).
// bins: [{ lo, hi, count, share }] in data units; markers: [{ x, label, cls }]
// draws vertical percentile uprights over the distribution.
export function histogram({
  bins = [],
  markers = [],
  width = 720,
  height = 220,
  formatX = compactUsd,
  barCls = 'chart-hist-bar',
  ariaLabel = 'Distribution',
  shareLabel = 'Share of simulations',
} = {}) {
  const usable = bins.filter(bin =>
    Number.isFinite(Number(bin?.lo)) && Number.isFinite(Number(bin?.hi)) && Number.isFinite(Number(bin?.count)));
  if (!usable.length) return '';
  const plot = plotArea(width, height);
  const xMin = Number(usable[0].lo);
  const xMax = Number(usable[usable.length - 1].hi);
  if (xMax <= xMin) return '';
  const maxShare = Math.max(...usable.map(bin => Number(bin.share) || 0));
  if (maxShare <= 0) return '';
  const x = linearScale([xMin, xMax], [plot.left, plot.right]);
  const y = linearScale([0, maxShare * 1.08], [plot.bottom, plot.top]);

  const barShapes = usable
    .map(bin => {
      const share = Number(bin.share) || 0;
      if (share <= 0) return '';
      const left = x(Number(bin.lo));
      const right = x(Number(bin.hi));
      const top = y(share);
      const barWidth = Math.max(1, right - left - 1);
      return `<rect class="${esc(bin.cls || barCls)}" x="${rnd(left)}" y="${rnd(top)}" width="${rnd(barWidth)}" height="${rnd(plot.bottom - top)}"></rect>`;
    })
    .join('');

  const markerShapes = markers
    .filter(marker => Number.isFinite(Number(marker?.x)))
    .map((marker, index) => {
      const mx = rnd(x(Math.min(Math.max(Number(marker.x), xMin), xMax)));
      const cls = marker.cls ? ` ${esc(marker.cls)}` : '';
      const labelY = plot.top + 11 + (index % 2) * 13;
      const label = marker.label
        ? `<text class="chart-marker-label${cls}" x="${mx + 5}" y="${labelY}">${esc(marker.label)}</text>`
        : '';
      return `<line class="chart-marker${cls}" x1="${mx}" y1="${plot.top}" x2="${mx}" y2="${plot.bottom}"></line>${label}`;
    })
    .join('');

  const xTicks = niceTicks(xMin, xMax, 5)
    .filter(tick => tick >= xMin && tick <= xMax)
    .map(tick =>
      `<text class="chart-axis-label" text-anchor="middle" x="${rnd(x(tick))}" y="${plot.bottom + 16}">${esc(formatX(tick))}</text>`)
    .join('');
  const yTicks = niceTicks(0, maxShare, 3)
    .map(tick => {
      const ty = rnd(y(tick));
      return (
        `<line class="chart-grid" x1="${plot.left}" y1="${ty}" x2="${plot.right}" y2="${ty}"></line>` +
        `<text class="chart-axis-label" text-anchor="end" x="${plot.left - 8}" y="${ty + 3}">${esc(`${Math.round(tick * 10) / 10}%`)}</text>`
      );
    })
    .join('');

  return svgShell({
    width,
    height,
    ariaLabel,
    hover: hoverAttr({
      xKey: 'value',
      formatY: 'pct',
      plot,
      labels: hoverLabels(['share'], { share: shareLabel }),
      points: usable.map(bin => ({
        x: `${compactUsd(Number(bin.lo))}–${compactUsd(Number(bin.hi))}`,
        px: rnd((x(Number(bin.lo)) + x(Number(bin.hi))) / 2),
        values: { share: roundHover(Number(bin.share) || 0) },
      })),
    }),
    content: [
      yTicks,
      `<line class="chart-grid chart-baseline" x1="${plot.left}" y1="${plot.bottom}" x2="${plot.right}" y2="${plot.bottom}"></line>`,
      xTicks,
      barShapes,
      markerShapes,
    ].join(''),
  });
}

// Stacked area over a shared x. series: [{ key, cls }] bottom-to-top;
// rows carry per-series values already in data units.
export function stackedArea({
  rows = [],
  xKey = 'year',
  series = [],
  width = 720,
  height = 260,
  formatX = String,
  formatY = compactUsd,
  yTickCount = 4,
  ariaLabel = 'Composition over time',
  seriesLabels = {},
} = {}) {
  const usable = rows.filter(row => Number.isFinite(Number(row?.[xKey])));
  if (usable.length < 2 || !series.length) return '';
  const stacked = usable.map(row => {
    let running = 0;
    const levels = { base: 0 };
    for (const item of series) {
      running += Math.max(0, Number(row[item.key]) || 0);
      levels[item.key] = running;
    }
    return { x: Number(row[xKey]), levels, row };
  });
  const yMax = Math.max(...stacked.map(point => point.levels[series[series.length - 1].key]));
  if (yMax <= 0) return '';
  const plot = plotArea(width, height);
  const x = linearScale([stacked[0].x, stacked[stacked.length - 1].x], [plot.left, plot.right]);
  const y = linearScale([0, yMax * 1.04], [plot.bottom, plot.top]);

  const areaShapes = series
    .map((item, index) => {
      const lowerKey = index === 0 ? 'base' : series[index - 1].key;
      const upper = stacked.map(point => [x(point.x), y(point.levels[item.key])]);
      const lower = stacked.map(point => [x(point.x), y(point.levels[lowerKey])]);
      const d = bandPath(upper, lower);
      return d ? `<path class="${esc(item.cls || 'chart-area')}" d="${d}"></path>` : '';
    })
    .join('');
  const topLine = linePath(stacked.map(point => [x(point.x), y(point.levels[series[series.length - 1].key])]));

  const xValues = stacked.map(point => point.x);
  const step = Math.max(1, Math.ceil(xValues.length / 6));
  const xTicks = xValues
    .filter((_, index) => index % step === 0 || index === xValues.length - 1)
    .map(value =>
      `<text class="chart-axis-label" text-anchor="middle" x="${rnd(x(value))}" y="${plot.bottom + 16}">${esc(formatX(value))}</text>`)
    .join('');

  const hoverKeys = [...series.map(item => item.key)].reverse();
  return svgShell({
    width,
    height,
    ariaLabel,
    hover: hoverAttr({
      xKey,
      formatY: 'usd',
      plot,
      labels: hoverLabels(hoverKeys, seriesLabels),
      points: stacked.map(point => {
        const values = {};
        for (const key of hoverKeys) {
          const value = Number(point.row[key]);
          if (Number.isFinite(value)) values[key] = roundHover(value);
        }
        return { x: point.x, px: rnd(x(point.x)), values };
      }),
    }),
    content: [
      yAxis({ ticks: niceTicks(0, yMax, yTickCount), y, plot, formatY }),
      `<line class="chart-grid chart-baseline" x1="${plot.left}" y1="${plot.bottom}" x2="${plot.right}" y2="${plot.bottom}"></line>`,
      xTicks,
      areaShapes,
      topLine ? `<path class="chart-line-median chart-area-topline" d="${topLine}"></path>` : '',
    ].join(''),
  });
}
