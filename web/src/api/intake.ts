import { client, call } from './client'
import type { Quota } from './collaboration'
import { chatStream, type ChatActivity } from './chatStream'

export type Draft = { type: 'bug' | 'improvement' | 'feature'; title: string; description: string; expected_behavior?: string; steps_to_reproduce?: string }
export type ChatMode = 'feedback' | 'bug' | 'consultation'
export type Source = { path: string; url: string; kind: 'docs' | 'code'; line: number }
export type Snapshot = { ready: boolean; message?: string; tag?: string; revision?: string; refreshed_at?: string; stale?: boolean; warning?: string }
export type IntakeResult = { reply: string; draft: Draft | null; state: string; quota: Quota; sources: Source[]; snapshot?: Snapshot }
export const intake = {
  stream: (key: string, content: string, state: string | undefined, mode: ChatMode, onActivity: (activity: ChatActivity) => void, signal?: AbortSignal) => chatStream<IntakeResult>('/intake/messages', { content, state, mode }, key, onActivity, signal),
  quota: (key: string) => call<Quota>('GET', '/intake/quota', undefined, { 'X-Intake-Key': key }),
  knowledge: () => call<Snapshot>('GET', '/intake/knowledge'),
  send: async (key: string, content: string, state?: string, mode: ChatMode = 'feedback') => {
    const response = await client.post('/intake/messages', { content, state, mode }, { headers: { 'X-Intake-Key': key }, timeout: 110000 })
    return response.data.data as IntakeResult
  },
}
