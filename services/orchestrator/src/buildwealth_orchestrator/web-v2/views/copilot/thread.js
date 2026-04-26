// Thread renderer for Copilot.
// Groups messages by date and renders user/assistant in distinct editorial vocab.

import { html, raw, esc } from '../../lib/dom.js';
import { renderMarkdown } from './markdown.js';

const TIME_FMT = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
const DAY_FMT = new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
const MONEY_FMT = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
const GOAL_DATE_FMT = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });

export function renderThread(messages, { thinking } = {}) {
  if (!messages.length && !thinking) return '';
  const groups = groupByDay(messages);
  const blocks = [];
  for (const [dayKey, items] of groups) {
    blocks.push(html`<div class="day-divider">${dayKey}</div>`);
    for (const m of items) blocks.push(renderMessage(m));
  }
  if (thinking) blocks.push(renderThinking());
  return html`<div class="thread">${blocks}</div>`;
}

function renderMessage(m) {
  const role = m.role === 'user' ? 'user' : 'assistant';
  const ts = m.created_at ? formatTime(m.created_at) : '';
  const tools = role === 'assistant' && Array.isArray(m.metadata?.tool_calls) ? m.metadata.tool_calls : [];

  const bodyHtml = role === 'user'
    ? esc(String(m.content || ''))
    : raw(renderMarkdown(String(m.content || '')));

  return html`
    <article class="message ${role}">
      <header class="message-eyebrow">
        <span class="role-tag">${role === 'user' ? 'You asked' : 'Copilot'}</span>
        ${ts ? html`<span class="timestamp">${ts}</span>` : ''}
      </header>
      <div class="message-body ${role}">${bodyHtml}</div>
      ${tools.length ? raw(renderToolTraces(tools)) : ''}
    </article>
  `;
}

function renderToolTraces(tools) {
  return html`
    <div class="tool-traces">
      ${tools.map(t => raw(renderToolTrace(t)))}
    </div>
  `;
}

function renderToolTrace(t) {
  if (isProfileDraftTrace(t)) {
    return renderProfileDraftCard(t.result);
  }
  return html`
    <details class="tool-trace">
      <summary>
        called <span class="tool-name">${esc(t.name || 'tool')}</span>
        ${t.error ? html`· <span style="color:var(--oxblood);">errored</span>` : ''}
      </summary>
      <pre>${esc(formatTrace(t))}</pre>
    </details>
  `;
}

function isProfileDraftTrace(trace) {
  return trace?.name === 'draft_financial_profile_update'
    && trace?.result?.draft_kind === 'financial_profile_update'
    && trace?.result?.proposed_profile;
}

function renderProfileDraftCard(result) {
  const profile = result.proposed_profile || {};
  const sections = [
    renderItemSection('Income items', profile.income_items, 'monthly_amount_usd'),
    renderItemSection('Expense items', profile.expense_items, 'monthly_amount_usd'),
    renderItemSection('Debt items', profile.debt_items, 'balance_usd'),
    renderGoalSection(profile.goal_items),
    renderTaxSection(profile.tax_profile),
    renderPhysicalAssetSection(profile.physical_assets),
  ].filter(Boolean);
  const flagLine = profile.flags?.no_debt
    ? html`<p class="profile-draft-flag">No debt</p>`
    : '';
  const draftPayload = result.patch_payload || profile;
  const encoded = encodeURIComponent(JSON.stringify(draftPayload));

  return html`
    <article class="profile-draft-card">
      <p class="profile-draft-eyebrow">Review profile update</p>
      <p class="profile-draft-summary">${result.summary || 'Copilot drafted changes for your financial profile.'}</p>
      ${raw(sections.join(''))}
      ${raw(flagLine)}
      <div class="entry-actions">
        <button class="action-link" data-profile-draft="${encoded}">
          Apply profile update <span class="arrow">›</span>
        </button>
      </div>
    </article>
  `;
}

function renderItemSection(title, items, amountKey) {
  if (!Array.isArray(items) || !items.length) return '';
  return html`
    <div class="profile-draft-section">
      <p class="profile-draft-section-title">${title}</p>
      <ul>
        ${items.slice(0, 4).map(item => html`
          <li>
            <span>${item?.label || 'Untitled'}</span>
            ${item?.[amountKey] != null ? html`<b>${MONEY_FMT.format(Number(item[amountKey]) || 0)}</b>` : ''}
          </li>
        `)}
      </ul>
    </div>
  `;
}

function renderGoalSection(items) {
  if (!Array.isArray(items) || !items.length) return '';
  return html`
    <div class="profile-draft-section">
      <p class="profile-draft-section-title">Goal items</p>
      <ul>
        ${items.slice(0, 4).map(item => {
          const amount = item?.target_amount_usd != null
            ? MONEY_FMT.format(Number(item.target_amount_usd) || 0)
            : '';
          const details = [
            item?.target_date ? `Target ${formatGoalDate(item.target_date)}` : '',
            item?.priority ? `${titleCase(item.priority)} priority` : '',
          ].filter(Boolean);
          return html`
            <li class="profile-draft-goal">
              <div class="profile-draft-goal-row">
                <span>${item?.label || 'Untitled goal'}</span>
                ${amount ? html`<b>${amount}</b>` : ''}
              </div>
              ${details.length ? html`<p class="profile-draft-meta">${details.join(' · ')}</p>` : ''}
              ${item?.notes ? html`<p class="profile-draft-note">${item.notes}</p>` : ''}
            </li>
          `;
        })}
      </ul>
    </div>
  `;
}

function renderPhysicalAssetSection(items) {
  if (!Array.isArray(items) || !items.length) return '';
  return html`
    <div class="profile-draft-section">
      <p class="profile-draft-section-title">Physical assets</p>
      <ul>
        ${items.slice(0, 4).map(item => {
          const amount = item?.current_value_usd != null
            ? MONEY_FMT.format(Number(item.current_value_usd) || 0)
            : '';
          const details = [
            item?.asset_type ? titleCase(item.asset_type) : '',
            item?.purchase_date ? `Purchased ${formatGoalDate(item.purchase_date)}` : '',
            item?.annual_growth_rate != null ? `Growth ${formatPercent(item.annual_growth_rate)}/yr` : '',
          ].filter(Boolean);
          return html`
            <li class="profile-draft-asset">
              <div class="profile-draft-asset-row">
                <span>${item?.label || 'Untitled asset'}</span>
                ${amount ? html`<b>${amount}</b>` : ''}
              </div>
              ${details.length ? html`<p class="profile-draft-meta">${details.join(' · ')}</p>` : ''}
            </li>
          `;
        })}
      </ul>
    </div>
  `;
}

function renderTaxSection(taxProfile) {
  if (!taxProfile || typeof taxProfile !== 'object') return '';
  const filingStatus = String(taxProfile.filing_status || '').trim();
  const marginalTaxRate = taxProfile.marginal_tax_rate;
  const state = String(taxProfile.state || '').trim().toUpperCase();
  if (!filingStatus && marginalTaxRate == null && !state) return '';

  const details = [
    marginalTaxRate != null ? `Marginal ${formatPercent(marginalTaxRate)}` : '',
    state ? `State ${state}` : '',
  ].filter(Boolean);

  return html`
    <div class="profile-draft-section">
      <p class="profile-draft-section-title">Tax profile</p>
      <ul>
        <li class="profile-draft-tax">
          <span>${filingStatus ? titleCase(filingStatus) : 'Tax basics'}</span>
          ${details.length ? html`<p class="profile-draft-meta">${details.join(' · ')}</p>` : ''}
        </li>
      </ul>
    </div>
  `;
}

function formatGoalDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return GOAL_DATE_FMT.format(date);
}

function titleCase(value) {
  const text = String(value || '').replace(/[_-]+/g, ' ').trim();
  if (!text) return '';
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function formatPercent(value) {
  const percent = Number(value) * 100;
  if (!Number.isFinite(percent)) return String(value);
  return `${percent.toLocaleString('en-US', { maximumFractionDigits: 2 })}%`;
}

function formatTrace(trace) {
  const lines = [];
  if (trace.arguments && Object.keys(trace.arguments).length) {
    lines.push('// arguments');
    lines.push(JSON.stringify(trace.arguments, null, 2));
  }
  if (trace.error) {
    lines.push('');
    lines.push('// error');
    lines.push(String(trace.error));
  } else if (trace.result && Object.keys(trace.result || {}).length) {
    lines.push('');
    lines.push('// result');
    lines.push(JSON.stringify(trace.result, null, 2));
  }
  return lines.join('\n') || '(no payload)';
}

function renderThinking() {
  return html`
    <div class="thinking-line">
      <span class="role-tag" style="font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:0.18em;color:var(--gilt);">Copilot</span>
      <span>is thinking</span>
      <span class="dots"><span>·</span><span>·</span><span>·</span></span>
    </div>
  `;
}

function formatTime(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return TIME_FMT.format(d);
}

function groupByDay(messages) {
  const groups = new Map();
  for (const m of messages) {
    const d = m.created_at ? new Date(m.created_at) : new Date();
    const key = Number.isNaN(d.getTime()) ? 'today' : DAY_FMT.format(d);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(m);
  }
  return groups;
}
