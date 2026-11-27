/** 需求生命周期：用于列表轨迹、详情步骤条与看板分组。统一由 stages.ts 派生。 */

import { isTerminated, stageIndex, stageOf, stages } from './stages'

export type TrailStage = { key: string; label: string; short: string; statuses: string[] }

export const trailStages: TrailStage[] = stages.map(({ key, label, short, statuses }) => ({ key, label, short, statuses }))

export type TrailState = {
  /** 当前所处阶段下标，-1 表示不属于任何阶段（未知状态） */
  index: number
  stage: TrailStage | null
  /** 已终止：拒绝/暂缓/重复/撤回/关闭，轨迹整体置灰 */
  stopped: boolean
  progress: number
}

export function trailOf(status: string): TrailState {
  const index = stageIndex(status)
  return {
    index,
    stage: index >= 0 ? trailStages[index]! : null,
    stopped: isTerminated(status),
    progress: index >= 0 ? ((index + 1) / trailStages.length) * 100 : 0,
  }
}

/** 看板列与阶段一一对应，四列稳定、不出现空列。 */
export const boardColumns = stages.map(({ key, label, color, statuses }) => ({ key, label, color, statuses }))

export const boardColumnOf = (status: string) => stageOf(status).key
