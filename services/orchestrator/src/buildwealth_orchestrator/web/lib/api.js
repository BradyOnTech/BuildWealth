export async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.text();
  if (!body.trim()) {
    if (!response.ok) {
      throw new Error(response.statusText || `Request failed with ${response.status}`);
    }
    throw new Error(`Expected JSON response from ${url}, received an empty body.`);
  }

  let data;
  try {
    data = JSON.parse(body);
  } catch {
    if (response.ok) {
      throw new Error(`Expected JSON response from ${url}, received invalid JSON.`);
    }
    throw new Error(`Request to ${url} failed with ${response.status} ${response.statusText || 'Unknown status'}, and the error body was not valid JSON.`);
  }

  if (!response.ok) {
    const detail = data && typeof data === 'object' ? data.detail || data.message : null;
    if (detail) {
      throw new Error(detail);
    }
    throw new Error(response.statusText || `Request failed with ${response.status}`);
  }
  return data;
}
