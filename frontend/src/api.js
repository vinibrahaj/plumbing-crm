export async function api(path, options = {}) {
  const token = sessionStorage.getItem('plumb-token');
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...(options.body ? { body: JSON.stringify(options.body) } : {}),
  });
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== '/auth/login') {
      sessionStorage.removeItem('plumb-token');
      window.dispatchEvent(new Event('session-expired'));
    }
    const detail = Array.isArray(data.detail)
      ? data.detail.map(e => `${e.loc.slice(1).join('.')}: ${e.msg}`).join('; ')
      : data.detail;
    throw new Error(detail || 'Request failed');
  }
  return data;
}
