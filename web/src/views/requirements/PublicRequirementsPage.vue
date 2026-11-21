<template>
  <section class="public-page">
    <!-- ================= 主视觉 ================= -->
    <header class="hero" data-glow>
      <div class="hero-aurora a"></div>
      <div class="hero-aurora b"></div>
      <div class="hero-aurora c"></div>
      <svg class="hero-route" viewBox="0 0 520 260" fill="none" aria-hidden="true">
        <path d="M-20 214C70 214 92 150 158 150s74 58 132 58 78-86 148-86 84 62 132 62"
          stroke="url(#routeGrad)" stroke-width="1.6" stroke-dasharray="7 9" stroke-linecap="round" />
        <path d="M-20 240C78 240 106 196 168 196s70 40 126 40 84-64 150-64 82 44 130 44"
          stroke="url(#routeGrad)" stroke-width="1" stroke-dasharray="3 12" stroke-linecap="round" opacity=".55" />
        <circle cx="158" cy="150" r="4" fill="#7ef0cd" />
        <circle cx="290" cy="208" r="3" fill="#8e9dff" opacity=".8" />
        <circle cx="438" cy="124" r="4" fill="#ffc46b" />
        <defs>
          <linearGradient id="routeGrad" x1="0" y1="0" x2="520" y2="0">
            <stop stop-color="#7ef0cd" stop-opacity=".1" />
            <stop offset=".45" stop-color="#a9b4ff" stop-opacity=".75" />
            <stop offset="1" stop-color="#ffc46b" stop-opacity=".25" />
          </linearGradient>
        </defs>
      </svg>

      <div class="hero-body">
        <p class="hero-eyebrow"><span class="pip"></span>公开需求 · Public Roadmap</p>
        <h1>一起，把行影集<br class="br-md" />打磨得更好</h1>
        <p class="hero-sub">每个想法都会被认真阅读、评估，并沿着公开的轨迹走向发布。</p>
        <div class="hero-actions">
          <button class="hero-cta" type="button" @click="$emit('submit')">
            <el-icon :size="16"><Plus /></el-icon>提交需求
          </button>
          <button class="hero-ghost" type="button" @click="$emit('discuss')">
            <el-icon :size="15"><MagicStick /></el-icon>与 AI 聊聊
          </button>
        </div>
      </div>

      <div class="hero-stats" aria-label="需求统计">
        <div class="hero-stat">
          <span class="hs-label">全部需求</span>
          <strong class="hs-num">{{ stats.total }}</strong>
          <span class="hs-foot">累计收到</span>
        </div>
        <div class="hero-stat">
          <span class="hs-label"><i style="background:#a9b4ff"></i>已规划</span>
          <strong class="hs-num">{{ stats.planned }}</strong>
          <span class="hs-foot">进入排期</span>
        </div>
        <div class="hero-stat">
          <span class="hs-label"><i style="background:#7ef0cd"></i>开发中</span>
          <strong class="hs-num">{{ stats.developing }}</strong>
          <span class="hs-foot">正在实现</span>
        </div>
        <div class="hero-stat">
          <span class="hs-label"><i style="background:#ffc46b"></i>已完成</span>
          <strong class="hs-num">{{ stats.done }}</strong>
          <span class="hs-foot">已发布上线</span>
        </div>
      </div>
    </header>

    <!-- ================= 工具条 ================= -->
    <div class="public-toolbar">
      <el-input v-model="filters.q" clearable placeholder="搜索编号、标题或关键词…" :prefix-icon="Search"
        class="search" @keyup.enter="$emit('reload')" @clear="$emit('reload')" />
      <div class="type-seg" role="group" aria-label="需求类型">
        <button v-for="option in typeOptions" :key="option.value" type="button"
          :class="{ active: filters.type === option.value }" :aria-pressed="filters.type === option.value"
          @click="setType(option.value)">{{ option.label }}</button>
      </div>
      <el-select v-model="filters.status" clearable placeholder="全部状态" class="select" @change="$emit('reload')">
        <el-option v-for="status in statusOptions" :key="status" :label="statusLabel(status)" :value="status" />
        <el-option label="已关闭" value="closed" />
      </el-select>
      <el-select :model-value="sortBy" placeholder="最新更新" class="sort" @update:model-value="$emit('update:sortBy', String($event))">
        <el-option label="最新更新" value="updated" /><el-option label="最早提交" value="oldest" /><el-option label="关注最多" value="followers" />
      </el-select>
      <div class="view-toggle" role="group" aria-label="视图切换">
        <button type="button" :class="{ active: view === 'list' }" :aria-pressed="view === 'list'" title="列表视图" @click="view = 'list'">
          <el-icon :size="15"><List /></el-icon>
        </button>
        <button type="button" :class="{ active: view === 'board' }" :aria-pressed="view === 'board'" title="看板视图" @click="view = 'board'">
          <el-icon :size="15"><Grid /></el-icon>
        </button>
      </div>
    </div>

    <div class="result-meta">
      <span>{{ view === 'board' ? `${items.length} 条需求按进展分组` : `共 ${items.length} 条需求` }}</span>
      <span v-if="filters.q || filters.type || filters.status" class="filtering">
        已筛选
        <button type="button" @click="clearFilters">清除</button>
      </span>
    </div>

    <RequirementTable :items="items" :manager="manager" :user="user" :view="view" :loading="loading"
      @open="$emit('open', $event)" @action="$emit('action', $event)" />
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Grid, List, MagicStick, Plus, Search } from '@element-plus/icons-vue'
import RequirementTable from '../../RequirementTable.vue'
import { statusLabel } from '../../labels'
import type { Requirement, User } from '../../api'

const props = defineProps<{
  stats: { total: number; planned: number; developing: number; done: number }
  filters: { q: string; type: string; status: string }
  statusOptions: string[]
  sortBy: string
  items: Requirement[]
  manager: boolean
  user: User | null
  loading?: boolean
}>()

const emit = defineEmits<{
  reload: []
  submit: []
  discuss: []
  open: [item: Requirement]
  action: [payload: { item: Requirement; command: string }]
  'update:sortBy': [value: string]
}>()

const view = ref<'list' | 'board'>('list')
const typeOptions = [
  { label: '全部', value: '' },
  { label: '新功能', value: 'feature' },
  { label: '体验优化', value: 'improvement' },
  { label: '问题修复', value: 'bug' },
]

function setType(value: string) {
  props.filters.type = value
  emit('reload')
}
function clearFilters() {
  props.filters.q = ''
  props.filters.type = ''
  props.filters.status = ''
  emit('reload')
}
</script>

<style scoped>
.public-page { display: flex; flex-direction: column; }

/* ------------------------------- hero ------------------------------- */
.hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 30px;
  margin-bottom: 20px;
  padding: 34px 34px 30px;
  overflow: hidden;
  border-radius: 28px;
  color: #fff;
  background:
    linear-gradient(135deg, #151a33 0%, #222a5c 46%, #133f4a 100%);
  box-shadow: 0 30px 60px -40px rgba(21, 26, 51, .9), 0 1px 0 rgba(255, 255, 255, .08) inset;
}
.hero::after {
  content: "";
  position: absolute; inset: 0; pointer-events: none;
  background-image: var(--contour);
  background-size: 760px 760px;
  opacity: .5;
  mix-blend-mode: overlay;
}
.hero-aurora {
  position: absolute; border-radius: 50%; pointer-events: none;
  filter: blur(60px); opacity: .55;
}
.hero-aurora.a { width: 420px; height: 300px; top: -160px; left: -80px; background: #4a5cf0; animation: drift 18s ease-in-out infinite alternate; }
.hero-aurora.b { width: 360px; height: 280px; bottom: -170px; left: 34%; background: #1aa98a; animation: drift 22s ease-in-out infinite alternate-reverse; }
.hero-aurora.c { width: 300px; height: 240px; top: -120px; right: 4%; background: #b06a1a; opacity: .4; animation: drift 26s ease-in-out infinite alternate; }
@keyframes drift {
  from { transform: translate3d(0, 0, 0) scale(1); }
  to { transform: translate3d(40px, 24px, 0) scale(1.14); }
}
.hero-route { position: absolute; right: -20px; bottom: -10px; width: 520px; height: 260px; opacity: .55; pointer-events: none; }

.hero-body { position: relative; z-index: 1; min-width: 0; }
.hero-eyebrow {
  display: inline-flex; align-items: center; gap: 8px;
  margin: 0 0 14px;
  color: rgba(255, 255, 255, .74);
  font-size: 10.5px; font-weight: 700; letter-spacing: .18em; text-transform: uppercase;
}
.hero-eyebrow .pip {
  width: 6px; height: 6px; border-radius: 50%; background: #7ef0cd;
  box-shadow: 0 0 0 4px rgba(126, 240, 205, .18);
  animation: pulse-ring 2.6s ease-out infinite;
}
.hero h1 {
  margin: 0 0 12px;
  color: #fff;
  font-size: 33px; line-height: 1.22; font-weight: 800; letter-spacing: -.035em;
  text-shadow: 0 2px 24px rgba(9, 12, 28, .45);
}
.hero-sub { margin: 0 0 20px; color: rgba(255, 255, 255, .66); font-size: 13.5px; line-height: 1.6; max-width: 460px; }
.hero-actions { display: flex; flex-wrap: wrap; gap: 10px; }
.hero-cta, .hero-ghost {
  display: inline-flex; align-items: center; gap: 7px;
  min-height: 40px; padding: 0 17px;
  border-radius: 12px; font-size: 13px; font-weight: 650; cursor: pointer;
  transition: transform .18s var(--ease), background var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}
.hero-cta {
  border: 0; color: #14203a;
  background: linear-gradient(120deg, #ffffff, #d8f6ee);
  box-shadow: 0 10px 24px -14px rgba(255, 255, 255, .8);
}
.hero-cta:hover { transform: translateY(-1px); box-shadow: 0 16px 30px -16px rgba(255, 255, 255, .9); }
.hero-ghost {
  border: 1px solid rgba(255, 255, 255, .24);
  background: rgba(255, 255, 255, .07);
  color: #fff;
  backdrop-filter: blur(8px);
}
.hero-ghost:hover { background: rgba(255, 255, 255, .14); }

.hero-stats {
  position: relative; z-index: 1;
  display: grid; grid-template-columns: repeat(4, minmax(74px, auto)); gap: 10px;
}
.hero-stat {
  display: grid; align-content: start; gap: 2px;
  min-width: 84px; padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, .13);
  background: linear-gradient(160deg, rgba(255, 255, 255, .1), rgba(255, 255, 255, .03));
  backdrop-filter: blur(12px);
  transition: transform var(--dur) var(--ease), border-color var(--dur) var(--ease);
}
.hero-stat:hover { transform: translateY(-2px); border-color: rgba(255, 255, 255, .26); }
.hs-label {
  display: inline-flex; align-items: center; gap: 5px;
  color: rgba(255, 255, 255, .62); font-size: 10.5px; font-weight: 600; white-space: nowrap;
}
.hs-label i { width: 5px; height: 5px; border-radius: 50%; }
.hs-num {
  color: #fff; font-size: 27px; font-weight: 800; line-height: 1.15;
  letter-spacing: -.03em; font-variant-numeric: tabular-nums;
}
.hs-foot { color: rgba(255, 255, 255, .4); font-size: 10px; }

/* ------------------------------ toolbar ------------------------------ */
.public-toolbar {
  display: flex; flex-wrap: wrap; align-items: center; gap: 9px;
  padding: 10px;
  margin-bottom: 10px;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: color-mix(in srgb, var(--surface) 86%, transparent);
  backdrop-filter: blur(16px) saturate(1.2);
  box-shadow: var(--shadow-xs);
}
.public-toolbar .search { flex: 1 1 230px; min-width: 170px; }
.public-toolbar .select, .public-toolbar .sort { width: 124px; }
.type-seg {
  display: inline-flex; gap: 2px; padding: 3px;
  border-radius: 11px; background: var(--surface-3);
}
.type-seg button {
  min-height: 28px; padding: 0 11px; border: 0; border-radius: 8px;
  background: transparent; color: var(--ink-3);
  font-size: 12.5px; font-weight: 550; white-space: nowrap; cursor: pointer;
  transition: background var(--dur) var(--ease), color var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}
.type-seg button:hover { color: var(--ink); }
.type-seg button.active {
  background: var(--surface); color: var(--primary-deep); font-weight: 700;
  box-shadow: 0 1px 2px rgba(20, 27, 51, .08), 0 4px 10px -6px rgba(20, 27, 51, .2);
}
.view-toggle {
  display: inline-flex; gap: 2px; padding: 3px;
  border-radius: 11px; background: var(--surface-3);
}
.view-toggle button {
  display: grid; place-items: center;
  width: 30px; height: 28px; border: 0; border-radius: 8px;
  background: transparent; color: var(--ink-3); cursor: pointer;
  transition: background var(--dur) var(--ease), color var(--dur) var(--ease);
}
.view-toggle button:hover { color: var(--ink); }
.view-toggle button.active { background: var(--surface); color: var(--primary); box-shadow: 0 1px 3px rgba(20, 27, 51, .12); }
.public-toolbar .submit-requirement-btn { margin-left: auto; }

.result-meta {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  margin: 0 2px 10px;
  color: var(--ink-4); font-size: 12px;
}
.filtering { display: inline-flex; align-items: center; gap: 6px; }
.filtering button { border: 0; background: transparent; color: var(--primary); font-size: 12px; cursor: pointer; text-decoration: underline; text-underline-offset: 3px; }

@media (max-width: 1180px) {
  .hero { grid-template-columns: minmax(0, 1fr); align-items: start; }
  .hero-stats { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .hero-route { opacity: .35; }
}
@media (max-width: 860px) {
  .hero { padding: 22px 18px 18px; border-radius: 22px; gap: 16px; margin-bottom: 14px; }
  .hero h1 { font-size: 24px; }
  .br-md { display: none; }
  .hero-eyebrow { margin-bottom: 10px; font-size: 9.5px; }
  .hero-sub { font-size: 12px; margin-bottom: 14px; }
  .hero-actions { gap: 8px; }
  .hero-cta, .hero-ghost { min-height: 38px; font-size: 12.5px; }
  /* 移动端把四个指标压成一行，把首屏留给需求列表 */
  .hero-stats { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; }
  .hero-stat { min-width: 0; padding: 8px 9px; border-radius: 12px; gap: 1px; }
  .hs-label { font-size: 9.5px; gap: 4px; }
  .hs-num { font-size: 19px; }
  .hs-foot { display: none; }
  .public-toolbar { padding: 8px; gap: 8px; position: sticky; top: calc(var(--mbar-h) + 6px); z-index: 20; }
  .public-toolbar .search { flex: 1 1 100%; }
  .public-toolbar .select, .public-toolbar .sort { flex: 1 1 0; width: auto; }
  .type-seg { flex: 1 1 100%; overflow-x: auto; scrollbar-width: none; }
  .type-seg button { flex: 1; }
  .view-toggle { display: none; }
  .public-toolbar .submit-requirement-btn { margin-left: 0; flex: 1; }
}
@media (max-width: 560px) {
  .hero h1 { font-size: 22px; }
  .hero-actions .hero-cta, .hero-actions .hero-ghost { flex: 1; justify-content: center; }
}
</style>