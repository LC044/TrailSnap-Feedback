<template>
  <section class="dashboard-page">
    <div class="page-head dashboard-head">
      <div class="page-head-left">
        <div class="page-head-icon"><el-icon :size="23"><DataAnalysis /></el-icon></div>
        <div>
          <h1>需求总览</h1>
          <p class="sub">掌握需求规模、审核积压和版本推进情况。</p>
          <p class="desc">数据来自{{ manager ? '全部未删除需求' : '公开需求' }}，趋势按创建时间统计。</p>
        </div>
      </div>
      <div class="dashboard-controls">
        <div class="seg" role="group" aria-label="统计时间范围">
          <button v-for="option in ranges" :key="option" type="button" :class="{ active: range === option }"
            :disabled="option > points.length" :aria-pressed="range === option" @click="range = option">近 {{ option }} 天</button>
        </div>
        <span class="updated">更新于 {{ formatUpdatedAt(data.generated_at) }}</span>
        <el-button class="refresh-btn" size="small" circle :loading="loading" aria-label="刷新看板数据" @click="emit('reload')">
          <el-icon v-if="!loading" :size="14"><Refresh /></el-icon>
        </el-button>
      </div>
    </div>

    <DashboardKpi :data="data" :points="slicedPoints" :manager="manager" @navigate="emit('navigate', $event)" />

    <div v-if="insight" class="insight-bar">
      <span class="insight-ico"><el-icon :size="15"><InfoFilled /></el-icon></span>
      <span class="insight-text">{{ insight }}</span>
      <button v-if="data.pending_review && manager" type="button" @click="emit('navigate', 'admin')">
        去审核 <el-icon :size="12"><ArrowRight /></el-icon>
      </button>
    </div>

    <div class="dashboard-main-grid">
      <DashboardTrend :points="points" :range="range" />
      <DashboardStatus :data="data" />
    </div>

    <div class="dashboard-secondary-grid">
      <DashboardBreakdown :data="data" />
      <DashboardRanking :data="data" @open-detail="emit('open-detail', $event)" />
    </div>

    <p class="dashboard-footnote">
      口径说明：统计范围为{{ manager ? '未删除的全部需求' : '未删除的公开需求' }}；新增趋势按创建时间统计，完成、关闭与平均处理时长按最近更新时间估算。时间范围仅影响趋势图与顶部指标卡。
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowRight, DataAnalysis, InfoFilled, Refresh } from '@element-plus/icons-vue'
import type { Dashboard } from '../../api'
import DashboardKpi from './DashboardKpi.vue'
import DashboardTrend from './DashboardTrend.vue'
import DashboardStatus from './DashboardStatus.vue'
import DashboardBreakdown from './DashboardBreakdown.vue'
import DashboardRanking from './DashboardRanking.vue'
import { formatUpdatedAt, trendPoints } from './dashboardData'

const props = defineProps<{ data: Dashboard; loading?: boolean; manager?: boolean }>()
const emit = defineEmits<{
  reload: []
  navigate: [tab: 'public' | 'admin' | 'versions']
  'open-detail': [number: number]
}>()

const ranges = [7, 30, 90]
const range = ref(30)
const points = computed(() => trendPoints(props.data))
const slicedPoints = computed(() => points.value.slice(-range.value))
const insight = computed(() => {
  const pending = props.data.pending_review
  const recent = props.data.new_last_7_days
  const share = props.data.total ? ((pending / props.data.total) * 100).toFixed(1) : '0.0'
  if (pending > 0) return `当前有 ${pending} 条需求待审核，占全部需求 ${share}%；近 7 天新增 ${recent} 条。`
  return `近 7 天新增 ${recent} 条需求，目前没有待审核积压。`
})
</script>

<style scoped>
.dashboard-page { min-width: 0; }
.dashboard-head { align-items: center; }
.dashboard-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.updated { font-size: 11.5px; color: var(--ink-4); white-space: nowrap; }
.refresh-btn { margin-left: 0; }

.insight-bar {
  display: flex; align-items: center; gap: 10px;
  margin: 4px 0 16px; padding: 11px 14px;
  border-radius: 14px;
  border: 1px solid color-mix(in srgb, var(--primary) 16%, var(--line));
  background: linear-gradient(100deg, var(--primary-softer), var(--surface) 70%);
  color: var(--ink-2); font-size: 12.5px;
}
.insight-ico {
  display: grid; place-items: center; flex: none;
  width: 26px; height: 26px; border-radius: 8px;
  background: var(--primary-soft); color: var(--primary);
}
.insight-text { flex: 1; min-width: 0; line-height: 1.55; }
.insight-bar button {
  display: inline-flex; align-items: center; gap: 4px; flex: none;
  padding: 5px 11px; border: 0; border-radius: 8px;
  background: var(--surface); color: var(--primary-deep);
  font-size: 12px; font-weight: 650; cursor: pointer;
  box-shadow: var(--shadow-xs);
  transition: background var(--dur) var(--ease), transform .16s var(--ease);
}
.insight-bar button:hover { background: var(--primary-soft); transform: translateX(1px); }

.dashboard-main-grid {
  display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(320px, 1fr);
  gap: 16px; align-items: stretch; margin-bottom: 16px;
}
.dashboard-secondary-grid {
  display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(320px, 1fr);
  gap: 16px; align-items: stretch;
}
.dashboard-footnote { margin: 16px 2px 0; font-size: 11.5px; line-height: 1.65; color: var(--ink-4); }

@media (max-width: 1180px) {
  .dashboard-main-grid, .dashboard-secondary-grid { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 760px) {
  .dashboard-head { align-items: flex-start; }
  .dashboard-controls { width: 100%; }
  .updated { display: none; }
  .insight-bar { flex-wrap: wrap; }
  .insight-bar button { margin-left: auto; }
}
</style>