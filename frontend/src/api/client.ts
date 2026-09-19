// 子路径部署（门户 /altium/）时 BASE_URL=/altium/ → API 走 /altium/api/v1
const BASE = `${(import.meta.env.BASE_URL ?? '/').replace(/\/$/, '')}/api/v1`

let token: string | null = localStorage.getItem('aidrive_token')

export function setToken(t: string | null) {
  token = t
  if (t) localStorage.setItem('aidrive_token', t)
  else localStorage.removeItem('aidrive_token')
}

export function getToken() {
  return token
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export function buildQuery(params: Record<string, unknown>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const s = search.toString()
  return s ? `?${s}` : ''
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string>) }
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (init?.body && !(init.body instanceof FormData)) headers['Content-Type'] = 'application/json'
  const resp = await fetch(`${BASE}${path}`, { ...init, headers })
  if (resp.status === 401) {
    setToken(null)
    window.location.hash = '#/login'
    throw new ApiError(401, '登录已过期')
  }
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`
    try {
      const data = await resp.json()
      detail = data.detail ?? detail
    } catch {
      /* ignore */
    }
    throw new ApiError(resp.status, detail)
  }
  if (resp.status === 204) return undefined as T
  return (await resp.json()) as T
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  postForm: <T,>(path: string, form: FormData) => request<T>(path, { method: 'POST', body: form }),
  put: <T,>(path: string, body: unknown) => request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  delete: <T,>(path: string) => request<T>(path, { method: 'DELETE' }),
  blob: async (path: string) => {
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`
    const resp = await fetch(`${BASE}${path}`, { headers })
    if (!resp.ok) throw new ApiError(resp.status, `HTTP ${resp.status}`)
    return URL.createObjectURL(await resp.blob())
  },
}

export interface ChatStreamEvent {
  type: 'meta' | 'delta' | 'error' | 'done'
  conversationId?: string
  title?: string
  text?: string
  message?: string
  messageId?: string
  durationMs?: number
}

export async function streamChat(body: Record<string, unknown>, onEvent: (e: ChatStreamEvent) => void) {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const resp = await fetch(`${BASE}/ai/chat/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
  if (!resp.ok || !resp.body) {
    let detail = `HTTP ${resp.status}`
    try {
      detail = (await resp.json()).detail ?? detail
    } catch {
      /* ignore */
    }
    onEvent({ type: 'error', message: detail })
    return
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const part of parts) {
      for (const line of part.split('\n')) {
        if (line.startsWith('data:')) {
          try {
            onEvent(JSON.parse(line.slice(5).trim()) as ChatStreamEvent)
          } catch {
            /* ignore malformed */
          }
        }
      }
    }
  }
}
