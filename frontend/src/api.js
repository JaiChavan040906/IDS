// Tiny fetch wrapper: adds the login token, parses JSON, turns errors into messages.
const TOKEN_KEY = 'ids_token'

export const getToken = () => {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export const setToken = (t) => {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t)
    else localStorage.removeItem(TOKEN_KEY)
  } catch { /* private mode */ }
}

export async function api(path, { method = 'GET', body, params } = {}) {
  const url = new URL(`/api${path}`, window.location.origin)
  if (params) Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v)
  })
  const res = await fetch(url, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401 && path !== '/auth/login') {
    setToken(null)
    window.dispatchEvent(new Event('ids-logout'))
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const d = data.detail
    throw new Error(Array.isArray(d) ? d.map((x) => `${x.loc?.at(-1)}: ${x.msg}`).join('; ') : d || res.statusText)
  }
  return data
}

// Upload one file as multipart form data (the browser sets the boundary header itself).
export async function apiUpload(path, file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`/api${path}`, {
    method: 'POST',
    headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {},
    body: form,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : res.statusText)
  return data
}

// Formatting helpers used across pages
export const pct = (x, d = 2) => (x === null || x === undefined ? '–' : `${(100 * x).toFixed(d)}%`)
export const num = (x) => (x === null || x === undefined ? '–' : Number(x).toLocaleString())
export const time = (t) => (t ? new Date(t).toLocaleString() : '–')
export const ago = (t) => {
  if (!t) return '–'
  const s = Math.max(0, (Date.now() - new Date(t).getTime()) / 1000)
  if (s < 60) return `${Math.floor(s)}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}
export const PROTO = { 6: 'TCP', 17: 'UDP', 1: 'ICMP', 0: 'HOPOPT' }
