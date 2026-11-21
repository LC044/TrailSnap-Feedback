<template>
  <div class="kpi-grid">
    <button v-for="(card, index) in cards" :key="card.key" type="button" class="kpi-card" :class="`tone-${card.tone}`"
      data-glow :style="{ animationDelay: `${index * 45}ms` }"
      :aria-label="`${card.label} ${formatNumber(card.value)}，${card.hint}`" @click="go(card)">
      <div class="kpi-glow" aria-hidden="true"></div>
      <div class="kpi-top">
        <span class="kpi-icon"><el-icon :size="16"><component :is="card.icon" /></el-icon></span>
        <span class="kpi-label">{{ card.label }}</span>
        <el-icon class="kpi-arrow" :size="13"><ArrowRight /></el-icon>
      </div>
      <div class="kpi-main">
        <strong class="kpi-value">{{ formatNumber(card.value) }}</strong>
        <span v-if="card.badge" class="kpi-badge" :class="card.badgeTone">{{ card.badge }}</span>
      </div>
      <p class="kpi-hint">{{ card.hint }}</p>
      <svg v-if="card.spark.length > 1" class="kpi-spark" viewBox="0 0 100 34" preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <linearGradient :id="`spark-${card.key}`" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" :stop-color="card.color" stop-opacity=".26" />
            <stop offset="100%" :stop-color="card.color" stop-opacity="0" />
          </linearGradient>
        </defs>
        <path :d="sparkArea(card.spark)" :fill="`url(#spark-${card.key})`" />
        <path :d="sparkLine(card.spark)" fill="none" :stroke="card.color" stroke-width="1.8"
          stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
      </svg>
      <div v-if="card.bar !== undefined" class="kpi-bar">
        <span :style="{ width: `${Math.min(100, card.bar)}%`, background: card.color }" />
      </div>
    </button>
  </div>

  <div class="kpi-strip">
    <div v-for="item in strip" :key="item.label" class="kpi-mini">
      <el-icon :size="14"><component :is="item.icon" /></el-icon>
      <span class="mini-label">{{ item.label }}</span>
      <strong>{{ item.value }}</strong>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue'
import { ArrowRight, CircleCheck, Clock, Connection, DataAnalysis, Files, Hide, Star, Timer, TrendCharts, User } from '@element-plus/icons-vue'
import type { Dashboard } from '../../api'
import { formatNumber, palette, type TrendPoint } from './dashboardData'

type NavTab = 'public' | 'admin' | 'versions'
type KpiCard = {
  key: string; label: string; value: number; hint: string; icon: Component; tone: string; color: string
  spark: number[]; bar?: number; tab?: NavTab; badge?: string; badgeTone?: 'up' | 'down'
}

const props = defineProps<{ data: Dashboard; points: TrendPoint[]; manager?: boolean }>()
const emit = defineEmits<{ navigate: [tab: NavTab] }>()

const sum = (values: number[]) => values.reduce((total, value) => total + value, 0)
const pct = (value: number) => props.data.total ? (value / props.data.total) * 100 : 0
const last7 = computed(() => sum(props.points.slice(-7).map(point => point.count)))
const prev7 = computed(() => sum(props.points.slice(-14, -7).map(point => point.count)))
const changePct = computed(() => prev7.value ? Math.round(((last7.value - prev7.value) / prev7.value) * 100) : null)

const cards = computed<KpiCard[]>(() => [
  {
    key: 'total', label: '全部需求', value: props.data.total, tab: 'public',
    hint: `近 ${props.points.length || 30} 天新增 ${formatNumber(sum(props.points.map(point => point.count)))} 条`,
    icon: DataAnalysis, tone: 'blue', color: palette.blue,
    spark: props.points.map(point => point.count),
  },
  {
    key: 'new', label: '近 7 天新增', value: props.data.new_last_7_days, tab: 'public',
    hint: changePct.value === null ? '等待更多历史数据' : `较前 7 天${changePct.value >= 0 ? '增长' : '下降'} ${Math.abs(changePct.value)}%`,
    icon: TrendCharts, tone: 'violet', color: palette.violet,
    spark: props.points.slice(-14).map(point => point.count),
    badge: changePct.value === null ? undefined : `${changePct.value >= 0 ? '+' : ''}${changePct.value}%`,
    badgeTone: (changePct.value ?? 0) >= 0 ? 'up' : 'down',
  },
  {
    key: 'pending', label: '待处理', value: props.data.pending_review, tab: props.manager ? 'admin' : 'public',
    hint: `占全部需求 ${pct(props.data.pending_review).toFixed(1)}%${props.manager ? ' · 建议优先审核' : ''}`,
    icon: Timer, tone: 'amber', color: palette.amber, spark: [], bar: pct(props.data.pending_review),
  },
  {
    key: 'progress', label: '开发发布中', value: props.data.in_progress, tab: 'versions',
    hint: `占全部需求 ${pct(props.data.in_progress).toFixed(1)}% · 版本推进中`,
    icon: CircleCheck, tone: 'teal', color: palette.teal, spark: [], bar: pct(props.data.in_progress),
  },
])

const strip = computed(() => [
  { label: '已关联 GitHub', value: formatNumber(props.data.github_linked), icon: Connection },
  { label: '匿名提交', value: formatNumber(props.data.anonymous), icon: Hide },
  { label: '参与人数', value: formatNumber(props.data.contributor_count), icon: Files },
  { label: '近 30 天活跃', value: props.data.active_contributors_30d === undefined ? '—' : formatNumber(props.data.active_contributors_30d), icon: User },
  { label: '关注总数', value: formatNumber(props.data.follower_count), icon: Star },
  { label: '近 30 天完成', value: props.data.released_last_30d === undefined ? '—' : formatNumber(props.data.released_last_30d), icon: CircleCheck },
  { label: '平均处理时长', value: props.data.avg_resolution_days == null ? '—' : `${props.data.avg_resolution_days} 天`, icon: Clock },
])

function go(card: KpiCard) {
  if (card.tab) emit('navigate', card.tab)
}

function sparkCoords(values: number[]) {
  const max = Math.max(1, ...values)
  return values.map((value, index) => ({
    x: values.length > 1 ? (index / (values.length - 1)) * 100 : 0,
    y: 32 - (value / max) * 27,
  }))
}
/* 用三次贝塞尔把折线柔化成曲线，避免稀疏数据出现台阶 */
const sparkLine = (values: number[]) => {
  const points = sparkCoords(values)
  if (points.length < 2) return points[0] ? `M${points[0].x.toFixed(1)},${points[0].y.toFixed(1)}` : ''
  let path = `M${points[0]!.x.toFixed(1)},${points[0]!.y.toFixed(1)}`
  for (let index = 1; index < points.length; index += 1) {
    const from = points[index - 1]!, to = points[index]!
    const midX = ((from.x + to.x) / 2).toFixed(1)
    path += ` C${midX},${from.y.toFixed(1)} ${midX},${to.y.toFixed(1)} ${to.x.toFixed(1)},${to.y.toFixed(1)}`
  }
  return path
}
const sparkArea = (values: number[]) => {
  if (values.length < 2) return ''
  return `${sparkLine(values)} L100,34 L0,34 Z`
}
</script>

<style scoped>
.kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.kpi-card {
  --kpi-color: var(--primary); --kpi-soft: var(--primary-soft);
  position: relative; display: block; min-width: 0; min-height: 150px;
  padding: 16px 17px 15px;
  overflow: hidden; text-align: left; cursor: pointer;
  border: 1px solid var(--line); border-radius: 18px;
  background: var(--surface);
  box-shadow: var(--shadow-xs);
  animation: rise .5s var(--ease-out) both;
  transition: transform .22s var(--ease), box-shadow .22s var(--ease), border-color .22s var(--ease);
}
.kpi-card:hover {
  transform: translateY(-3px);
  border-color: color-mix(in srgb, var(--kpi-color) 32%, var(--line));
  box-shadow: 0 18px 36px -24px color-mix(in srgb, var(--kpi-color) 90%, transparent), var(--shadow-sm);
}
.kpi-card:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.kpi-glow {
  position: absolute; inset: 0; pointer-events: none; opacity: 0;
  background: radial-gradient(220px circle at var(--mx, 50%) var(--my, 0%), color-mix(in srgb, var(--kpi-color) 12%, transparent), transparent 70%);
  transition: opacity .3s var(--ease);
}
.kpi-card:hover .kpi-glow { opacity: 1; }
.kpi-card::before {
  content: ""; position: absolute; inset: 0 0 auto 0; height: 2px;
  background: linear-gradient(90deg, var(--kpi-color), transparent 70%);
  opacity: .55;
}
.kpi-card.tone-violet { --kpi-color: var(--violet); --kpi-soft: var(--violet-soft); }
.kpi-card.tone-amber { --kpi-color: var(--accent); --kpi-soft: var(--accent-soft); }
.kpi-card.tone-teal { --kpi-color: var(--brand-teal); --kpi-soft: var(--brand-teal-soft); }

.kpi-top { position: relative; z-index: 1; display: flex; align-items: center; gap: 8px; }
.kpi-icon {
  display: inline-flex; align-items: center; justify-content: center; flex: none;
  width: 29px; height: 29px; border-radius: 9px;
  background: var(--kpi-soft); color: var(--kpi-color);
}
.kpi-label { font-size: 12.5px; color: var(--ink-2); font-weight: 600; white-space: nowrap; }
.kpi-arrow { margin-left: auto; color: var(--ink-5); opacity: 0; transform: translateX(-4px); transition: opacity .2s, transform .2s; }
.kpi-card:hover .kpi-arrow { opacity: 1; transform: none; }
.kpi-main { position: relative; z-index: 1; display: flex; align-items: baseline; gap: 8px; margin-top: 12px; }
.kpi-value {
  font-size: 33px; line-height: 1.05; font-weight: 800;
  letter-spacing: -.045em; color: var(--ink); font-variant-numeric: tabular-nums;
}
.kpi-badge {
  padding: 2px 7px; border-radius: 99px;
  font-size: 11px; font-weight: 700; font-variant-numeric: tabular-nums;
}
.kpi-badge.up { background: var(--success-soft); color: var(--success); }
.kpi-badge.down { background: var(--danger-soft); color: var(--danger); }
.kpi-hint { position: relative; z-index: 1; margin: 7px 0 0; font-size: 11.5px; line-height: 1.5; color: var(--ink-4); }
.kpi-spark {
  position: absolute; right: 0; bottom: 0;
  width: 52%; height: 44px; opacity: .55;
  pointer-events: none; z-index: 0;
  mask-image: linear-gradient(90deg, transparent 0%, #000 42%);
  -webkit-mask-image: linear-gradient(90deg, transparent 0%, #000 42%);
}
.kpi-bar { position: relative; z-index: 1; margin-top: 13px; height: 5px; border-radius: 99px; background: var(--surface-3); overflow: hidden; }
.kpi-bar span { display: block; height: 100%; border-radius: 99px; transition: width .6s var(--ease); }

.kpi-strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(132px, 1fr)); gap: 8px; margin: 12px 0 18px; }
.kpi-mini {
  display: flex; align-items: center; gap: 6px; min-width: 0;
  padding: 9px 11px;
  border: 1px solid var(--line); border-radius: 11px;
  background: color-mix(in srgb, var(--surface) 72%, transparent);
  transition: border-color var(--dur) var(--ease), background var(--dur) var(--ease);
}
.kpi-mini:hover { border-color: color-mix(in srgb, var(--primary) 26%, var(--line)); background: var(--surface); }
.kpi-mini .el-icon { flex: none; color: var(--ink-4); }
.kpi-mini .mini-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; color: var(--ink-3); }
.kpi-mini strong { margin-left: auto; flex: none; font-size: 12.5px; font-weight: 700; color: var(--ink); font-variant-numeric: tabular-nums; }

@media (max-width: 1080px) {
  .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .kpi-grid { gap: 9px; }
  .kpi-card { min-height: 128px; padding: 13px 13px 12px; border-radius: 15px; }
  .kpi-value { font-size: 25px; }
  .kpi-label { font-size: 12px; }
  .kpi-hint { font-size: 10.5px; }
  .kpi-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
  .kpi-mini { padding: 8px 9px; }
}
@media (max-width: 420px) {
  .kpi-grid { grid-template-columns: minmax(0, 1fr); }
  .kpi-card { min-height: 0; }
}
</style>