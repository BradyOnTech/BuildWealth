// Tiny DOM helpers. Tagged templates for HTML escaping by default.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value == null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'html') node.innerHTML = value;
    else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else {
      node.setAttribute(key, value === true ? '' : value);
    }
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
  }
  return node;
}

const ESCAPE_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
// Escapes once and marks the result already-safe, so `html\`\`` will not
// escape it a second time. (esc() inside html`` used to double-escape —
// visible whenever a value contained & < >, e.g. API validation messages.)
// Coerces to the escaped string in plain template literals via toString().
export function esc(str) {
  if (str == null) return rawObj('');
  const escaped = String(str).replace(/[&<>"']/g, ch => ESCAPE_MAP[ch]);
  return rawObj(escaped);
}

// Strip HTML to plain text. Some backend payloads (notably recommendation
// detail fields) arrive pre-wrapped in HTML for v1's innerHTML consumers;
// v2 displays them with editorial typography and wants plain prose.
const ENTITY_MAP = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'", '&nbsp;': ' ' };
export function stripHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/<[^>]*>/g, '')
    .replace(/&(?:amp|lt|gt|quot|#39|nbsp);/g, m => ENTITY_MAP[m] || m)
    .replace(/\s+/g, ' ')
    .trim();
}

// Tagged template — auto-escapes interpolations unless wrapped in raw().
// Returns a { __raw, value, toString } record so nested `html\`\`` calls survive
// interpolation without double-escape, while still coercing cleanly to a string
// for innerHTML assignment, Array.join, and plain template literals.
export function html(strings, ...values) {
  let out = '';
  for (let i = 0; i < strings.length; i++) {
    out += strings[i];
    if (i < values.length) {
      const v = values[i];
      if (v == null || v === false) continue;
      if (v && typeof v === 'object' && v.__raw) out += v.value;
      else if (Array.isArray(v)) {
        for (const part of v) {
          if (part == null || part === false) continue;
          if (part && typeof part === 'object' && part.__raw) out += part.value;
          else out += esc(part);
        }
      }
      else out += esc(v);
    }
  }
  return rawObj(out);
}

// Mark a value as already-safe HTML (skip escaping in html``).
export const raw = (value) => rawObj(value ?? '');

function rawObj(str) {
  const s = typeof str === 'string' ? str : String(str ?? '');
  return { __raw: true, value: s, toString() { return s; } };
}

export function setView(rootEl, markup) {
  rootEl.innerHTML = markup;
}

export function delegate(rootEl, eventType, selector, handler) {
  rootEl.addEventListener(eventType, (e) => {
    const target = e.target.closest(selector);
    if (target && rootEl.contains(target)) handler(e, target);
  });
}
