export async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail || data.message || response.statusText;
    throw new Error(detail);
  }
  return data;
}
