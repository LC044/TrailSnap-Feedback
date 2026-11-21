/** 需求生命周期：用于列表轨迹、详情步骤条与看板分组。 */

export type TrailStage = { key: string; label: string; short: string; statuses: string[] }

export const trailStages: TrailStage[] = [
  { key: 'intake', label: '已提交', short: '提交', statuses: ['submitted', 'triaging', 'withdrawn'] },
  { key: 'review', label: '评估中', short: '评估', statuses: ['pending_review', 'needs_information'] },
  { key: 'planned', label: '已规划', short: '规划', statuses: ['candidate', 'accepted', 'scheduled', 'planning', 'candidate_selection', 'scope_locked'] },
  { key: 'building', label: '开发中', short: '开发', statuses: ['developing', 'testing', 'release_ready', 'pr_open', 'merged', 'paused', 'blocked'] },
  { key: 'shipped', label: '已发布', short: '发布', statuses: ['released', 'published', 'completed'] },
]

const closedStatuses = ['closed', 'rejected', 'duplicate', 'deferred', 'cancelled']

export type TrailState = {
  /** 当前所处阶段下标，-1 表示未进入主流程（重复/关闭等） */
  index: number
  stage: TrailStage | null
  stopped: boolean
  progress: number
}

export function trailOf(status: string): TrailState {
  const index = trailStages.findIndex(stage => stage.statuses.includes(status))
  const stopped = closedStatuses.includes(status)
  return {
    index: stopped ? -1 : index,
    stage: index >= 0 ? trailStages[index]! : null,
    stopped,
    progress: stopped ? 0 : ((index + 1) / trailStages.length) * 100,
  }
}

/** 看板分组：合并为六列，保证列数稳定、可横向浏览。 */
export const boardColumns: Array<{ key: string; label: string; color: string; statuses: string[] }> = [
  { key: 'intake', label: '待分析', color: 'var(--info)', statuses: ['submitted', 'triaging'] },
  { key: 'review', label: '待审核', color: 'var(--warning)', statuses: ['pending_review', 'needs_information'] },
  { key: 'planned', label: '已规划', color: 'var(--violet)', statuses: ['candidate', 'accepted', 'scheduled', 'planning', 'candidate_selection', 'scope_locked'] },
  { key: 'building', label: '开发中', color: 'var(--primary)', statuses: ['developing', 'testing', 'release_ready', 'pr_open', 'merged', 'paused', 'blocked'] },
  { key: 'shipped', label: '已发布', color: 'var(--success)', statuses: ['released', 'published', 'completed'] },
  { key: 'closed', label: '已关闭', color: 'var(--ink-4)', statuses: closedStatuses },
]

export const boardColumnOf = (status: string) =>
  boardColumns.find(column => column.statuses.includes(status))?.key ?? 'closed'