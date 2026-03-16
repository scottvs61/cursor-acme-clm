/**
 * API client: base URL and auth header. Token is read from sessionStorage.
 */
const API_BASE = '/api'

export function apiUrl(path) {
  const p = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE}${p}`
}

export function authHeaders() {
  const token = sessionStorage.getItem('clm_token')
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  return headers
}

export async function apiFetch(path, options = {}) {
  const url = apiUrl(path)
  const res = await fetch(url, { ...options, headers: { ...authHeaders(), ...options.headers } })
  if (res.status === 401) {
    sessionStorage.removeItem('clm_token')
    sessionStorage.removeItem('clm_user')
    throw new Error('Unauthorized')
  }
  return res
}
