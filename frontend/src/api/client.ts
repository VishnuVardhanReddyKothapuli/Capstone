import type { CheckResult, CheckType, HistoryPage, ModelInfo, TokenResponse, User } from '../types'

const TOKEN_KEY = 'sentinal.token'
export class ApiError extends Error { constructor(readonly status: number, message: string) { super(message); this.name = 'ApiError' } }
let token: string | null = localStorage.getItem(TOKEN_KEY)
let onUnauthorized: (() => void) | null = null
export const getToken = () => token
export function setToken(next: string | null) { token = next; if (next) localStorage.setItem(TOKEN_KEY, next); else localStorage.removeItem(TOKEN_KEY) }
export const setUnauthorizedHandler = (handler: (() => void) | null) => { onUnauthorized = handler }
function withAuth(headers: Record<string, string> = {}) { return token ? { ...headers, Authorization: `Bearer ${token}` } : headers }
function errorMessage(response: Response): string {
  // Response bodies are never shown: an upstream service could contain internals.
  return { 400: 'Please check the submitted information.', 403: 'You do not have access to this resource.', 404: 'The requested item was not found.', 409: 'That username or email is already in use.', 413: 'The selected file is too large.', 415: 'Please choose a supported image file.', 422: 'Please check the submitted information.', 429: 'Please wait a moment and try again.', 503: 'The service is temporarily unavailable. Please try again.' }[response.status] ?? 'Something went wrong. Please try again.'
}
const API_BASE = import.meta.env.VITE_API_URL || ''

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  const response = await fetch(url, { ...init, headers: withAuth(init.headers as Record<string, string> | undefined) })
  if (response.status === 401) {
    if (path.startsWith('/api/auth/login')) {
      throw new ApiError(401, 'Incorrect username or password.')
    }
    onUnauthorized?.()
    throw new ApiError(401, 'Your session has expired. Please sign in again.')
  }
  if (!response.ok) throw new ApiError(response.status, errorMessage(response))
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
function jsonPost<T>(path: string, payload: unknown) { return request<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }) }
export const api = {
  register: (username: string, password: string, email?: string) => jsonPost<TokenResponse>('/api/auth/register', { username, password, email: email || undefined }),
  login: (username: string, password: string) => jsonPost<TokenResponse>('/api/auth/login', { username, password }),
  me: () => request<User>('/api/auth/me'),
  moderate: (file: File, mode: CheckType) => { const form = new FormData(); form.append('file', file); form.append('mode', mode); return request<CheckResult>('/api/moderate', { method: 'POST', body: form }) },
  history: (options: { checkType?: CheckType | null; limit?: number; offset?: number } = {}) => { const params = new URLSearchParams(); if (options.checkType) params.set('check_type', options.checkType); params.set('limit', String(options.limit ?? 24)); params.set('offset', String(options.offset ?? 0)); return request<HistoryPage>(`/api/history?${params}`) },
  models: () => request<ModelInfo>('/api/models'),
  adminSummary: () => request<{ users: number; checks: number }>('/api/admin/summary'),
  explain: (checkId: number, refresh = false) => request<CheckResult>(`/api/checks/${checkId}/explain${refresh ? '?refresh=true' : ''}`, { method: 'POST' }),
  objectUrl: async (path: string) => { const url = path.startsWith('http') ? path : `${API_BASE}${path}`; const response = await fetch(url, { headers: withAuth() }); if (response.status === 401) onUnauthorized?.(); if (!response.ok) throw new ApiError(response.status, errorMessage(response)); return URL.createObjectURL(await response.blob()) },
}
