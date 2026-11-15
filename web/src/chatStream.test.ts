import { afterEach, describe, expect, it, vi } from 'vitest'
import { chatStream } from './api/chatStream'

afterEach(() => vi.unstubAllGlobals())
const frame = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
const ok = (data: unknown) => ({ code: 0, msg: 'success', data })
function stream(parts: string[]) {
  return new Response(new ReadableStream({ start(controller) { for (const part of parts) controller.enqueue(new TextEncoder().encode(part)); controller.close() } }), { headers: { 'content-type': 'text/event-stream' } })
}
describe('chat activity stream', () => {
  it('handles split frames, activity and final answer in one admitted POST', async () => {
    const activity = { kind: 'search_official_docs', label: '检索官网文档', status: 'completed' }
    const body = frame('activity', ok(activity)) + frame('result', ok({ reply: '回答', state: 'signed' }))
    const fetcher = vi.fn().mockResolvedValue(stream([body.slice(0, 17), body.slice(17, 43), body.slice(43)]))
    vi.stubGlobal('fetch', fetcher)
    const seen = vi.fn()
    expect(await chatStream('/intake/messages', { content: '行影集' }, 'key', seen)).toEqual({ reply: '回答', state: 'signed' })
    expect(seen).toHaveBeenCalledWith(activity)
    expect(fetcher).toHaveBeenCalledOnce()
  })
  it('preserves admission cooldown errors without automatically retrying', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ msg: '请稍候' }), { status: 429, headers: { 'Retry-After': '20' } }))
    vi.stubGlobal('fetch', fetcher)
    await expect(chatStream('/intake/messages', {}, 'key', vi.fn())).rejects.toMatchObject({ response: { status: 429, headers: { 'retry-after': '20' } } })
    expect(fetcher).toHaveBeenCalledOnce()
  })
  it('reports a broken stream or server error without accepting a partial reply', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream([': keepalive\n\n'])))
    await expect(chatStream('/intake/messages', {}, 'key', vi.fn())).rejects.toThrow('未收到完整回复')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream([frame('error', { code: 503, msg: '暂不可用', data: null })])))
    await expect(chatStream('/intake/messages', {}, 'key', vi.fn())).rejects.toThrow('暂不可用')
  })
})
