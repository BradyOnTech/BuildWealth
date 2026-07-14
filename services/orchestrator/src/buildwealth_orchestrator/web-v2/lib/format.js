// Formatting helpers — tabular numbers, currency, percent, dates.
// All return strings; callers compose into HTML.

const USD = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

const USD_CENTS = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 2,
});

const PCT = new Intl.NumberFormat('en-US', {
  style: 'percent',
  maximumFractionDigits: 1,
  minimumFractionDigits: 0,
});

const PCT_PT = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 1,
  minimumFractionDigits: 0,
});

const SIGNED = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
  signDisplay: 'always',
});

export function fmtUsd(value, { cents = false } = {}) {
  if (value == null || Number.isNaN(value)) return '—';
  return cents ? USD_CENTS.format(value) : USD.format(value);
}

export function fmtUsdSigned(value) {
  if (value == null || Number.isNaN(value)) return '—';
  return SIGNED.format(value);
}

// Splits a USD string into { currency: "$", number: "1,247,832" }
// so the "$" can render at smaller weight in the hero treatment.
export function splitUsd(value) {
  const text = fmtUsd(value);
  const match = text.match(/^(-?)(\$)([\d,]+(?:\.\d+)?)$/);
  if (!match) return { currency: '', number: text };
  const [, sign, currency, number] = match;
  return { currency, number: `${sign}${number}` };
}

export function fmtPct(value, { fromFraction = false } = {}) {
  if (value == null || Number.isNaN(value)) return '—';
  return fromFraction ? PCT.format(value) : `${PCT_PT.format(value)}%`;
}

export function fmtPctSigned(value, { fromFraction = false } = {}) {
  if (value == null || Number.isNaN(value)) return '—';
  const pct = fromFraction ? value * 100 : value;
  const sign = pct > 0 ? '+' : '';
  return `${sign}${PCT_PT.format(pct)}%`;
}

// Coercing "or dash" variants. Unlike fmtUsd/fmtPct these accept numeric
// strings (form inputs) and treat blank ('' / null / undefined / non-numeric)
// as absent, rendering the dash. Pass a different `dash` when a view wants
// its own vocabulary for "unset" (e.g. plan story uses 'app default').
export function fmtUsdOrDash(value, dash = '—') {
  value = unwrapDisplayValue(value);
  if (value == null || value === '') return dash;
  const n = Number(value);
  if (!Number.isFinite(n)) return dash;
  return fmtUsd(n);
}

// Fraction in (0.05 == 5%), two decimals out. For percent-point inputs or
// other precisions, format at the call site.
export function fmtPctOrDash(value, dash = '—') {
  value = unwrapDisplayValue(value);
  if (value == null || value === '') return dash;
  const n = Number(value);
  if (!Number.isFinite(n)) return dash;
  return `${(n * 100).toFixed(2)}%`;
}

// APIs may attach provenance as { value, source, ... }. Views should display
// the value while never allowing an arbitrary object to become
// "[object Object]" in a customer-facing table.
export function unwrapDisplayValue(value) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return Object.prototype.hasOwnProperty.call(value, 'value') ? value.value : null;
  }
  return value;
}

// Null in, null out — for callers that hide the whole line when a value is
// absent rather than printing a dash.
export function fmtUsdOrEmpty(value) {
  if (value == null) return null;
  return fmtUsd(value);
}

const DATELONG = new Intl.DateTimeFormat('en-US', {
  weekday: 'long',
  month: 'long',
  day: 'numeric',
  year: 'numeric',
});

const TIME = new Intl.DateTimeFormat('en-US', {
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
  timeZoneName: 'short',
});

export function fmtDateLong(value) {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  return DATELONG.format(d);
}

export function fmtTimeShort(value) {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  return TIME.format(d);
}

export function fmtRelative(value, { now = new Date() } = {}) {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  const minutes = Math.round((now - d) / 60000);
  if (minutes < 1) return 'moments ago';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

const ROMANS = ['I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII'];
export function roman(n) {
  if (n < 1) return '';
  return ROMANS[n - 1] || String(n);
}
