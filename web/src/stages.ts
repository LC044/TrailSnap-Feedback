/**
 * 对外展示的四个阶段。内部 status 仍保留 18 个（见 labels.ts），
 * 这里只做归并：列表徽章、看板列、筛选器、详情步骤条、统计分组全部读这一份。
 */
export type StageKey = 'pending' | 'planned' | 'building' | 'done'

export type Stage = {
  key: StageKey
  label: string
  short: string
  color: string
  /** 该阶段包含的内部状态，顺序不影响展示。 */
  statuses: string[]
}

export const stages: Stage[] = [
  {
    key: 'pending', label: '待处理', short: '待处理', color: 'var(--warning)',
    statuses: ['submitted', 'triaging', 'pending_review', 'needs_information'],
  },
  {
    key: 'planned', label: '已规划', short: '规划', color: 'var(--violet)',
    statuses: ['candidate', 'accepted', 'scheduled', 'planning', 'candidate_selection', 'scope_locked'],
  },
  {
    key: 'building', label: '开发中', short: '开发', color: 'var(--primary)',
    statuses: ['developing', 'testing', 'release_ready', 'pr_open', 'merged', 'paused', 'blocked'],
  },
  {
    key: 'done', label: '已完成', short: '完成', color: 'var(--success)',
    statuses: ['released', 'published', 'completed', 'closed', 'rejected', 'deferred', 'duplicate', 'withdrawn', 'cancelled'],
  },
]

/** 已终止（不再推进）的内部状态，用于列表轨迹置灰。 */
const terminated = ['closed', 'rejected', 'deferred', 'duplicate', 'withdrawn', 'cancelled']
export const isTerminated = (status: string) => terminated.includes(status)

export const stageOf = (status: string): Stage =>
  stages.find(stage => stage.statuses.includes(status)) ?? stages[stages.length - 1]!

export const stageIndex = (status: string): number =>
  stages.findIndex(stage => stage.statuses.includes(status))

/** 列表徽章用：只展示阶段名，精确状态放 title 里。 */
export const stageLabel = (status: string) => stageOf(status).label
export const stageKeyOf = (status: string) => stageOf(status).key

/** 筛选器给后端的参数：一个阶段可能对应多个内部状态，用逗号拼接。 */
export const stageStatusParam = (key: string) =>
  stages.find(stage => stage.key === key)?.statuses.join(',') ?? key

export const stageOptions = stages.map(stage => ({ value: stage.key, label: stage.label }))
