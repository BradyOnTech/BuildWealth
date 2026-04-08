export const byId = (id) => document.getElementById(id);

const logEl = () => byId('log');

export function stamp() {
  return new Date().toLocaleTimeString();
}

export function writeLog(message, payload = null, isError = false) {
  const el = logEl();
  if (!el) return;
  const lines = [`[${stamp()}] ${message}`];
  if (payload !== null) lines.push(JSON.stringify(payload, null, 2));
  const block = document.createElement('div');
  if (isError) block.classList.add('error');
  block.textContent = `${lines.join('\n')}\n`;
  el.prepend(block);
}

export function fmtCurrency(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
}

export function fmtPct(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-';
  return `${value.toFixed(2)}%`;
}

export function fmtDate(value) {
  if (!value) return '-';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString();
}

export function fmtAgeMinutes(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-';
  if (value < 60) return `${value}m`;
  const hours = Math.floor(value / 60);
  const minutes = value % 60;
  if (hours < 48) return `${hours}h ${minutes}m`;
  const days = Math.floor(hours / 24);
  return `${days}d ${hours % 24}h`;
}

export function truncate(value, maxLength = 120) {
  const text = String(value || '').trim();
  return text.length <= maxLength ? text : `${text.slice(0, maxLength - 3)}...`;
}

export function uid(prefix) {
  return `${prefix}-${Math.random().toString(16).slice(2, 10)}`;
}

export function parseOptionalNumber(value, label) {
  const text = String(value || '').trim();
  if (!text) return null;
  const n = Number(text);
  if (Number.isNaN(n)) throw new Error(`${label} must be numeric.`);
  return n;
}

export function parseOptionalNumericField(rawValue, fieldLabel, asInteger = false) {
  const text = String(rawValue || '').trim();
  if (!text) return { present: false, value: null };
  const n = Number(text);
  if (Number.isNaN(n)) throw new Error(`${fieldLabel} must be numeric.`);
  if (asInteger && !Number.isInteger(n)) throw new Error(`${fieldLabel} must be an integer.`);
  return { present: true, value: n };
}

export function formatNumericInput(value, maxDecimals = 6) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '';
  if (Number.isInteger(value)) return String(value);
  return String(Number(value.toFixed(maxDecimals)));
}
