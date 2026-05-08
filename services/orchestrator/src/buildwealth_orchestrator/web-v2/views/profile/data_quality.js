// Profile · Data Quality tab.
// Two passes through the same question — what does BuildWealth trust?
//   I.  Pending review: context candidates that target profile fields,
//       with deep-links to the owning section so the user can resolve them.
//   II. Confirmed sources: every profile field that has metadata, ordered by
//       freshness so stale entries are visible.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtRelative } from '../../lib/format.js';

const FIELD_LABELS = {
  'tax_profile.filing_status':       'Filing status',
  'tax_profile.marginal_tax_rate':   'Marginal tax rate',
  'tax_profile.effective_tax_rate':  'Effective tax rate',
  'tax_profile.state_tax_rate':      'State tax rate',
  'tax_profile.state':               'State',
  'investment_policy.max_single_symbol_exposure_pct': 'Single-investment limit',
  'investment_policy.max_sector_exposure_pct':        'Single-sector limit',
  'investment_policy.minimum_cash_runway_months':     'Minimum cash cushion',
  'investment_policy.risk_tolerance':                 'Risk comfort',
  'investment_policy.tax_sensitivity':                'Tax sensitivity',
  'investment_policy.simplicity_preference':          'Simplicity preference',
  'investment_policy.minimum_research_confidence':    'Required research confidence',
  'investment_policy.restricted_symbols':             'Restricted symbols',
  'investment_policy.restricted_sectors':             'Restricted sectors',
  'flags.no_debt':                                    'No-debt flag',
  'flags.no_goals':                                   'No-goals flag',
};

const SECTION_FOR_AREA = {
  tax_profile:       'taxes',
  investment_policy: 'investing',
  investing:         'investing',
  flags:             'overview',
  income:            'income',
  income_items:      'income',
  expenses:          'expenses',
  expense_items:     'expenses',
  debt:              'debt',
  debt_items:        'debt',
  goals:             'goals',
  goal_items:        'goals',
  assets:            'assets',
  physical_assets:   'assets',
};

export function renderDataQuality(ui) {
  const candidates = (ui.candidates || []).filter(isProfileTargeted);
  const metadataEntries = profileMetadataEntries(ui.profile?.profile_metadata);

  return html`
    <div class="profile-data-quality">
      <header class="profile-table-head">
        <div>
          <p class="profile-table-eyebrow">§ Foundation · Data quality</p>
          <h2 class="profile-table-title">What BuildWealth trusts</h2>
          <p class="profile-table-lede">
            Every material profile fact has a source and a status. Pending suggestions
            need your review before BuildWealth treats them as authoritative.
          </p>
        </div>
      </header>

      ${raw(pendingCard(candidates))}
      ${raw(confirmedCard(metadataEntries))}
    </div>
  `;
}

/* ─────────────  Pending candidates  ───────────── */

function pendingCard(candidates) {
  if (!candidates.length) {
    return html`
      <article class="profile-card profile-card-quiet">
        <header class="profile-card-head">
          <h3 class="profile-card-title">Pending review</h3>
        </header>
        <p class="profile-card-empty">
          Nothing pending. BuildWealth has no unresolved suggestions about your profile.
        </p>
      </article>
    `;
  }

  const items = candidates.slice(0, 12).map(c => `
    <li class="profile-quality-item">
      <div class="profile-quality-meta">
        <span class="profile-quality-area">${esc(humanArea(c))}</span>
        <span class="profile-quality-confidence">${esc(c.confidence || 'medium')} confidence</span>
      </div>
      <p class="profile-quality-claim">${esc(c.extracted_claim || c.headline || c.title || 'Suggested context update')}</p>
      <div class="profile-quality-actions">
        ${c.review_route
          ? `<a class="link-editorial" href="${esc(routeAsHash(c.review_route))}" data-route>Open owning section</a>`
          : sectionForCandidate(c)
            ? `<a class="link-editorial" href="${esc(`#profile?section=${sectionForCandidate(c)}`)}" data-route>Open owning section</a>`
            : ''}
        <a class="link-editorial muted" href="#inbox" data-route>Resolve in Inbox</a>
      </div>
    </li>
  `).join('');

  return html`
    <article class="profile-card profile-card-attn">
      <header class="profile-card-head">
        <h3 class="profile-card-title">Pending review</h3>
        <span class="profile-card-count">${candidates.length}</span>
      </header>
      <ul class="profile-quality-list">
        ${raw(items)}
      </ul>
    </article>
  `;
}

/* ─────────────  Confirmed metadata  ───────────── */

function confirmedCard(entries) {
  if (!entries.length) {
    return html`
      <article class="profile-card profile-card-quiet">
        <header class="profile-card-head">
          <h3 class="profile-card-title">Confirmed sources</h3>
        </header>
        <p class="profile-card-empty">
          No fields have recorded sources yet. As you confirm rows, BuildWealth
          stores who said what so Copilot's reasoning stays inspectable.
        </p>
      </article>
    `;
  }

  const items = entries.map(({ path, meta }) => {
    const label = FIELD_LABELS[path] || humanFieldPath(path);
    const status = meta.status || 'recorded';
    const tone = toneForStatus(status, meta);
    const updated = meta.updated_at || meta.last_confirmed_at;
    return `
      <li class="profile-quality-item">
        <div class="profile-quality-meta">
          <span class="profile-quality-area">${esc(label)}</span>
          <span class="status-pill ${esc(tone)}">
            <span class="dot"></span>${esc(humanStatus(status))}
          </span>
        </div>
        <p class="profile-quality-claim">
          ${esc(`Source: ${humanWord(meta.source) || 'unspecified'}`)}
          ${meta.confidence ? esc(` · ${meta.confidence} confidence`) : ''}
          ${updated ? esc(` · updated ${fmtRelative(updated)}`) : ''}
        </p>
      </li>
    `;
  }).join('');

  return html`
    <article class="profile-card">
      <header class="profile-card-head">
        <h3 class="profile-card-title">Confirmed sources</h3>
        <span class="profile-card-count">${entries.length}</span>
      </header>
      <ul class="profile-quality-list">
        ${raw(items)}
      </ul>
    </article>
  `;
}

/* ─────────────  Helpers  ───────────── */

function isProfileTargeted(candidate) {
  const domain = String(candidate?.target_domain || '').toLowerCase();
  if (domain === 'profile' || domain === 'financial_profile') return true;
  // Fall back to anything that names a profile-shaped review route — keeps
  // legacy candidates without target_domain visible in the right place.
  const route = String(candidate?.review_route || '').toLowerCase();
  return route.startsWith('#profile') || route.startsWith('/v2#profile');
}

function profileMetadataEntries(metadata) {
  if (!metadata || typeof metadata !== 'object') return [];
  const entries = [];
  for (const [path, value] of Object.entries(metadata)) {
    if (!value || typeof value !== 'object') continue;
    entries.push({ path, meta: value });
  }
  // Stalest first — confirmed-but-old fields are the most useful to surface.
  entries.sort((a, b) => freshness(b.meta) - freshness(a.meta));
  return entries;
}

function freshness(meta) {
  const t = meta.updated_at || meta.last_confirmed_at;
  return t ? Date.now() - new Date(t).getTime() : Number.MAX_SAFE_INTEGER;
}

function humanArea(candidate) {
  const area = candidate?.target_area || candidate?.target_domain || 'profile';
  const field = candidate?.target_field;
  if (field) return `${humanWord(area)} · ${humanWord(field)}`;
  return humanWord(area);
}

function sectionForCandidate(candidate) {
  const area = String(candidate?.target_area || '').toLowerCase();
  return SECTION_FOR_AREA[area] || null;
}

function routeAsHash(route) {
  if (!route) return '';
  const trimmed = String(route).trim();
  if (trimmed.startsWith('#')) return trimmed;
  if (trimmed.startsWith('/v2#')) return trimmed.slice(3);
  if (trimmed.startsWith('/')) return `#${trimmed.slice(1)}`;
  return trimmed;
}

function humanFieldPath(path) {
  return String(path || '').replace(/[._]/g, ' ');
}

function humanWord(value) {
  if (!value) return '';
  return String(value).replace(/_/g, ' ');
}

function humanStatus(status) {
  const map = {
    user_confirmed:       'Confirmed',
    confirmed:            'Confirmed',
    pending_review:       'Pending review',
    needs_review:         'Pending review',
    stale:                'Stale',
    superseded:           'Superseded',
    rejected:             'Rejected',
    authoritative_after_apply: 'Confirmed',
  };
  return map[String(status).toLowerCase()] || humanWord(status) || 'Recorded';
}

function toneForStatus(status, meta) {
  const s = String(status).toLowerCase();
  if (s.includes('confirm') || meta.confirmed_by_user) return 'applied';
  if (s.includes('pending') || s.includes('review'))  return 'proposed';
  if (s === 'stale')                                  return 'stale';
  if (s.includes('reject'))                           return 'rejected';
  return 'archived';
}
