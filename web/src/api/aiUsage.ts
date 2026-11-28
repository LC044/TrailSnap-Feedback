import { call } from './client'

export type ConversationKind = 'requirement' | 'intake'
export type UsageCounts = {
  requests: number; failed: number; unreported: number
  input_tokens: number; output_tokens: number; reserved_tokens: number
}
export type AIConversation = UsageCounts & {
  id: string; updated_at: string; requirement_number: number | null; title: string | null; has_transcript: boolean
}
export type AIToolCall = { name: string; created_at: string; status: 'completed' | 'failed' | 'unconfirmed' }
export type AIMessage = UsageCounts & {
  id: string; created_at: string; mode: string; status: string; content: string; response: string | null; image_count: number; file_count: number
  tool_calls: AIToolCall[] | null
}
export type ModelUsage = UsageCounts & { connection_name: string; model_name: string; today_tokens: number }
type Page<T> = { total: number; items: T[] }

export const aiUsage = {
  models: () => call<{ models: ModelUsage[] }>('GET', '/admin/ai-model-usage'),
  conversations: (kind: ConversationKind, page: number) => call<Page<AIConversation>>('GET', `/admin/ai-conversations?kind=${kind}&page=${page}`),
  messages: (id: string, page: number, kind: ConversationKind) => call<Page<AIMessage>>('GET', `/admin/ai-conversations/${encodeURIComponent(id)}?kind=${kind}&page=${page}`),
}

export type ActivityCounts = { active_accounts: number; anonymous_sessions: number; conversations: number; turns: number; retries: number }
export type OverviewCounts = UsageCounts & ActivityCounts
export type UsageSource = 'all' | 'intake' | 'requirement' | 'background'
export type AIOverview = {
  tracking_since: string | null
  summary: OverviewCounts
  trend: (OverviewCounts & { day: string })[]
  sources: (OverviewCounts & { kind: Exclude<UsageSource, 'all'> })[]
  models: (UsageCounts & { id: string; connection_name: string; model_name: string })[]
}
export const loadAIOverview = (days: number, source: UsageSource) => call<AIOverview>('GET', `/admin/ai-overview?days=${days}&source=${source}`)
