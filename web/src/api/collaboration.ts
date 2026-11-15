import { call } from './client'

export type Message = { id: string; content: string; response?: string; mode: string; status: string; error?: string; created_at: string }
export type Quota = { daily_used: number; daily_limit: number; daily_remaining: number; conversation_used: number; conversation_limit: number; interval_seconds: number; reset_after_seconds: number }
export type Conversation = { messages: Message[]; can_plan: boolean; quota: Quota }
export type Delivery = { id: string; kind: string; status: string; attempts: number; last_error?: string; created_at: string }
const headers = (token?: string) => token ? { 'X-Requirement-Edit-Token': token } : undefined
export const collaboration = {
  read: (id: string, token?: string) => call<Conversation>('GET', `/requirements/${id}/conversation`, undefined, headers(token)),
  send: (id: string, content: string, client_id: string, mode: string, token?: string) => call<Message>('POST', `/requirements/${id}/conversation`, { content, client_id, mode }, headers(token)),
  retry: (id: string, message: string, token?: string) => call<Message>('POST', `/requirements/${id}/conversation/${message}/retry`, undefined, headers(token)),
  subscribe: (id: string, email: string, token?: string) => call('POST', `/requirements/${id}/notifications`, { email }, headers(token)),
  consult: (id: string, body: string) => call('POST', `/requirements/${id}/consultations`, { body }),
  confirm: (action: string, token: string) => call('POST', `/notifications/${action}`, { token }),
  deliveries: () => call<Delivery[]>('GET', '/admin/notifications'),
  retryDelivery: (id: string) => call('POST', `/admin/notifications/${id}/retry`),
}
