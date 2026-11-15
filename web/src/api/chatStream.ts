import { API_BASE_URL } from '../runtimeBase'

export type ChatActivity = { kind: string; label: string; status: 'running' | 'completed' | 'failed' }
type Envelope = { code: number; msg: string; data: any }

function failure(code: number, message: string, retryAfter?: string | null) {
  return Object.assign(new Error(message), { response: { status: code, data: { msg: message }, headers: { 'retry-after': retryAfter } } })
}

/** One admitted POST, never retried automatically when the connection breaks. */
export async function chatStream<T>(path: string, body: unknown, key: string, onActivity: (activity: ChatActivity) => void, signal?: AbortSignal): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', Accept: 'text/event-stream', 'X-Intake-Key': key }
  try { const token = localStorage.getItem('rp_token'); if (token) headers.Authorization = `Bearer ${token}` } catch { /* Anonymous browser. */ }
  const controller = new AbortController()
  const abort = () => controller.abort()
  signal?.addEventListener('abort', abort, { once: true })
  if (signal?.aborted) abort()
  const timer = setTimeout(abort, 110000)
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
  try {
    const response = await fetch(`${API_BASE_URL.replace(/\/$/, '')}/${path.replace(/^\//, '')}`, { method: 'POST', headers, body: JSON.stringify(body), signal: controller.signal, credentials: 'same-origin' })
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw failure(response.status, payload.msg || payload.detail || '暂时无法连接，请稍后重试', response.headers.get('retry-after'))
    }
    if (!response.headers.get('content-type')?.includes('text/event-stream') || !response.body) throw failure(503, '连接中断，请稍后重试')
    reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = '', bytes = 0
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      bytes += value.byteLength
      if (bytes > 300000) throw failure(503, '回复过长，请稍后重试')
      buffer += decoder.decode(value, { stream: true }).replace(/\r/g, '')
      let end: number
      while ((end = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, end); buffer = buffer.slice(end + 2)
        const kind = frame.split('\n').find(line => line.startsWith('event:'))?.slice(6).trim()
        const raw = frame.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
        if (!raw) continue
        const data: Envelope = JSON.parse(raw)
        if (kind === 'error' || data.code !== 0) throw failure(data.code || 503, data.msg)
        if (kind === 'activity') onActivity(data.data as ChatActivity)
        if (kind === 'result') return data.data as T
      }
      if (buffer.length > 150000) throw failure(503, '回复过长，请稍后重试')
    }
    throw failure(503, '连接中断，未收到完整回复；请稍后重试')
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', abort)
    await reader?.cancel().catch(() => {})
  }
}
