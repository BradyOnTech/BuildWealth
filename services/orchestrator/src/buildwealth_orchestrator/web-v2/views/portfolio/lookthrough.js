// Movement II addendum — Look-through.
// Opens covered funds into estimated company / sector / region exposure so
// three overlapping index funds read as what they are: one bet, bought thrice.
// Estimates only (seeded top-10 constituents), and the card says so.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtUsd, fmtPct } from '../../lib/format.js';
import { humanizeAllocationKey } from './composition.js';

export function renderLookThrough(report) {
  const coverage = report?.coverage || {};
  const coveredCount = Number(coverage.covered_fund_count || 0);

  return html`
    <div class="lookthrough-card" style="margin-top: var(--s-6);">
      <header class="section-head" style="margin-bottom: var(--s-3);">
        <span class="section-eyebrow">Look-through</span>
        ${coveredCount ? html`<p class="section-lede">${coverageLine(coverage)}</p>` : ''}
      </header>
      ${coveredCount ? raw(renderBody(report)) : raw(renderEmpty(report))}
    </div>
  `;
}

function renderEmpty(report) {
  const unknown = Array.isArray(report?.coverage?.unknown_funds) ? report.coverage.unknown_funds : [];
  const hint = unknown.length
    ? `No constituent estimates for ${unknown.slice(0, 4).join(', ')} yet — look-through covers common broad funds.`
    : 'Hold a broad fund like VTI or VOO and this card opens it up into the companies, sectors, and regions inside.';
  return html`<p class="fit-empty">${hint}</p>`;
}

function renderBody(report) {
  const companies = rows(report?.effective_company_exposure).slice(0, 8);
  const sectors = rows(report?.sector_exposure).slice(0, 5);
  const regions = rows(report?.region_exposure).slice(0, 5);
  const pairs = rows(report?.pairwise_fund_overlap).slice(0, 4);
  const notes = Array.isArray(report?.notes) ? report.notes.filter(Boolean) : [];

  return html`
    ${companies.length ? html`
      <div class="benchmark-rows" data-lookthrough-companies>
        ${raw(companies.map(companyRow).join(''))}
      </div>
    ` : ''}
    ${(sectors.length || regions.length) ? html`
      <div class="composition-grid" style="margin-top: var(--s-4);">
        ${raw(exposureBlock('Sectors, opened up', sectors))}
        ${raw(exposureBlock('Regions, opened up', regions))}
      </div>
    ` : ''}
    ${pairs.length ? html`
      <div class="benchmark-rows" style="margin-top: var(--s-4);" data-lookthrough-overlap>
        ${raw(pairs.map(overlapRow).join(''))}
      </div>
    ` : ''}
    ${raw(notes.map(note => html`<p class="marginalia">${note}</p>`.toString()).join(''))}
  `;
}

export function coverageLine(coverage = {}) {
  const covered = Number(coverage.covered_value_usd || 0);
  const totalFunds = Number(coverage.total_fund_value_usd || 0);
  const count = Number(coverage.covered_fund_count || 0);
  const unknown = Array.isArray(coverage.unknown_funds) ? coverage.unknown_funds.filter(Boolean) : [];
  let line = `Constituent estimates cover ${fmtUsd(covered)} of ${fmtUsd(totalFunds)} in funds `
    + `(${count} fund${count === 1 ? '' : 's'}).`;
  if (unknown.length) line += ` Not covered: ${unknown.slice(0, 4).join(', ')}.`;
  return line;
}

function companyRow(row) {
  const via = Array.isArray(row.via) ? row.via.map(v => String(v?.fund || '')).filter(Boolean) : [];
  return html`
    <div class="benchmark-row">
      <strong>${esc(String(row.symbol || '—'))}</strong>
      <span>${fmtPct(Number(row.exposure_pct || 0))}</span>
      <span>${fmtUsd(Number(row.exposure_usd || 0))}${via.length ? raw(` · via ${esc(via.slice(0, 4).join(', '))}`) : ''}</span>
    </div>
  `.toString();
}

function exposureBlock(label, entries) {
  return html`
    <div class="composition-block">
      <span class="composition-eyebrow">${label}</span>
      <div class="benchmark-rows">
        ${raw(entries.map(entry => html`
          <div class="benchmark-row">
            <strong>${esc(humanizeAllocationKey(entry.key))}</strong>
            <span>${fmtPct(Number(entry.exposure_pct || 0))}</span>
            <span>${fmtUsd(Number(entry.exposure_usd || 0))}</span>
          </div>
        `).join(''))}
      </div>
    </div>
  `.toString();
}

// "VTI and VOO share an estimated 33% of their weight" — the honest,
// plain-English version of a pairwise min-weight sum over top-10 holdings.
export function overlapSentence(pair = {}) {
  const pct = Math.round(Number(pair.overlap_weight || 0) * 100);
  return `${pair.fund_a || '?'} and ${pair.fund_b || '?'} share an estimated ${pct}% of their weight`;
}

function overlapRow(pair) {
  const shared = Array.isArray(pair.shared_top_holdings) ? pair.shared_top_holdings : [];
  return html`
    <div class="benchmark-row">
      <strong>${esc(`${pair.fund_a || '—'} · ${pair.fund_b || '—'}`)}</strong>
      <span class="delta-down">overlapping</span>
      <span>${esc(overlapSentence(pair))}${shared.length ? raw(` — shared: ${esc(shared.slice(0, 5).join(', '))}`) : ''}</span>
    </div>
  `.toString();
}

function rows(value) {
  return Array.isArray(value) ? value.filter(Boolean) : [];
}
