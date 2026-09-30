export type Role = 'admin' | 'analyst' | 'soc_manager'
export type User = { username: string; role: Role }
export type Alert = {
  id: number
  title: string
  severity: string
  status: string
  event_count: number
  context: Record<string, unknown>
  created_at: string
  incident_id: number | null
}
export type Incident = {
  id: number
  alert_id: number
  title: string
  severity: string
  status: string
  assignee: string | null
  created_at: string
  updated_at: string
  context: Record<string, any>
  event_count: number
  timeline?: { id: number; kind: string; content: string; author: string; created_at: string }[]
  events?: { id: number; event_type: string; source_ip: string; username: string; message: string; occurred_at: string }[]
  playbook_runs?: { id: number; playbook_key: string; status: string; requested_by: string; approved_by: string | null; result: Record<string, any> }[]
}

const TOKEN_KEY = 'sentinel.access_token'
export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(path.startsWith('/api') ? path : `/api${path}`, { ...options, headers })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const detail = payload?.detail
    throw new Error(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((item: { msg: string }) => item.msg).join('; ') : `Erreur HTTP ${response.status}`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function login(username: string, password: string): Promise<User> {
  const form = new URLSearchParams({ username, password })
  const response = await fetch('/api/auth/token', { method: 'POST', body: form })
  const result = await response.json()
  if (!response.ok) throw new Error(result.detail || 'Connexion impossible')
  localStorage.setItem(TOKEN_KEY, result.access_token)
  return { username: result.username, role: result.role }
}