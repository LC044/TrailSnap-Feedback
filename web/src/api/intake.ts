import { client, call } from './client'
import type { Quota } from './collaboration'

export type Draft = { type: 'bug' | 'improvement' | 'feature'; title: string; description: string; expected_behavior?: string; steps_to_reproduce?: string }
export type IntakeResult = { reply: string; draft: Draft | null; state: string; quota: Quota }
export const intake = {
  quota: (key: string) => call<Quota>('GET', '/intake/quota', undefined, { 'X-Intake-Key': key }),
  send: async (key: string, content: string, state?: string) => {
    const response = await client.post('/intake/messages', { content, state }, { headers: { 'X-Intake-Key': key }, timeout: 110000 })
    return response.data.data as IntakeResult
  },
}
