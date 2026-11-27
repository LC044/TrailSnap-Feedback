<template>
  <section class="public-page">
    <header class="roadmap-header">
      <div class="roadmap-intro">
        <div class="roadmap-mark"><el-icon :size="21"><Collection /></el-icon></div>
        <div>
          <h1>公开需求</h1>
          <p>查看行影集的开发进度，提交你遇到的问题或想实现的功能。</p>
        </div>
      </div>
      <div class="roadmap-actions">
        <el-button type="primary" size="large" :icon="Plus" @click="$emit('submit')">提交需求</el-button>
        <el-button size="large" :icon="MagicStick" @click="$emit('discuss')">与 AI 讨论</el-button>
      </div>
    </header>

    <dl class="roadmap-stats" aria-label="需求统计">
      <div v-for="item in metrics" :key="item.key" class="roadmap-stat">
        <dt><span class="stat-icon" :class="item.key"><el-icon :size="17"><component :is="item.icon" /></el-icon></span>{{ item.label }}</dt>
        <dd>{{ stats[item.key] }}</dd>
      </div>
    </dl>

    <section class="roadmap-results" aria-labelledby="requirements-title">
      <div class="results-heading">
        <h2 id="requirements-title">需求列表</h2>
        <span v-if="!loading && !error">{{ items.length }} 条需求</span>
      </div>
      <div class="public-toolbar">
        <el-input v-model="filters.q" clearable placeholder="搜索编号、标题或关键词…" :prefix-icon="Search"
          aria-label="搜索需求" class="search" @keyup.enter="$emit('reload')" @clear="$emit('reload')" />
        <div class="type-seg" role="group" aria-label="需求类型">
          <button v-for="option in typeOptions" :key="option.value" type="button"
            :class="{ active: filters.type === option.value }" :aria-pressed="filters.type === option.value"
            @click="setType(option.value)">{{ option.label }}</button>
        </div>
        <el-select v-model="filters.status" clearable placeholder="全部状态" aria-label="需求状态" class="select" @change="$emit('reload')">
          <el-option v-for="option in statusOptions" :key="option.value" :label="option.label" :value="option.value" />
        </el-select>
        <el-select :model-value="sortBy" placeholder="最新更新" aria-label="排序方式" class="sort" @update:model-value="$emit('update:sortBy', String($event))">
          <el-option label="最新更新" value="updated" /><el-option label="最早提交" value="oldest" /><el-option label="关注最多" value="followers" />
        </el-select>
        <div class="view-toggle" role="group" aria-label="视图切换">
          <button type="button" :class="{ active: view === 'list' }" :aria-pressed="view === 'list'" aria-label="列表视图" title="列表视图" @click="view = 'list'">
            <el-icon :size="15"><List /></el-icon>
          </button>
          <button type="button" :class="{ active: view === 'board' }" :aria-pressed="view === 'board'" aria-label="看板视图" title="看板视图" @click="view = 'board'">
            <el-icon :size="15"><Grid /></el-icon>
          </button>
        </div>
        <button v-if="filters.q || filters.type || filters.status" type="button" class="clear-filters" @click="clearFilters">清除</button>
      </div>

      <div v-if="error" class="panel empty" role="status">
        <strong>{{ error }}</strong>
        <el-button :icon="Refresh" @click="$emit('reload')">重试</el-button>
      </div>
      <RequirementTable v-else :items="items" :manager="manager" :user="user" :view="view" :loading="loading"
        @open="$emit('open', $event)" @action="$emit('action', $event)" />
    </section>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { CircleCheck, Collection, Grid, List, MagicStick, Plus, Refresh, Search, Timer, Tools } from '@element-plus/icons-vue'
import RequirementTable from '../../RequirementTable.vue'
import type { Requirement, User } from '../../api'

const props = defineProps<{
  stats: { total: number; planned: number; developing: number; done: number }
  filters: { q: string; type: string; status: string }
  statusOptions: { value: string; label: string }[]
  sortBy: string
  items: Requirement[]
  manager: boolean
  user: User | null
  loading?: boolean
  error?: string
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

const metrics = [
  { key: 'total', label: '全部需求', icon: Collection },
  { key: 'planned', label: '已规划', icon: Timer },
  { key: 'developing', label: '开发中', icon: Tools },
  { key: 'done', label: '已完成', icon: CircleCheck },
] as const
</script>

<style scoped>
.roadmap-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px 24px;
  padding: clamp(18px, 2.5vw, 28px);
  background: var(--rp-card);
  border: 1px solid var(--rp-border);
  border-radius: var(--rp-radius);
}
.roadmap-intro { display: flex; align-items: center; gap: 14px; min-width: 0; }
.roadmap-mark, .stat-icon {
  display: inline-grid;
  place-items: center;
  flex: none;
  background: var(--rp-primary-soft);
  color: var(--rp-primary-dark);
}
.roadmap-mark { width: 42px; height: 42px; border-radius: 12px; }
.roadmap-intro h1 { font-size: clamp(25px, 2.6vw, 34px); line-height: 1.18; }
.roadmap-intro p { margin-top: 8px; color: var(--rp-text-3); }
.roadmap-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.roadmap-actions .el-button + .el-button { margin-left: 0; }
.roadmap-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 16px 0 26px;
}
.roadmap-stat {
  padding: 13px 16px;
  border: 1px solid var(--rp-border);
  border-radius: var(--rp-radius);
  background: var(--rp-card);
}
.roadmap-stat dt { display: flex; align-items: center; gap: 8px; color: var(--rp-text-3); font-size: 13px; }
.roadmap-stat dd { margin: 4px 0 0; font-size: 25px; font-weight: 700; font-variant-numeric: tabular-nums; }
.stat-icon { width: 30px; height: 30px; border-radius: 9px; }
.stat-icon.planned { background: var(--warning-soft); color: var(--warning); }
.stat-icon.developing { background: var(--violet-soft); color: var(--violet); }
.stat-icon.done { background: var(--success-soft); color: var(--success); }
.results-heading { display: flex; align-items: baseline; gap: 10px; margin-bottom: 10px; }
.results-heading h2 { font-size: 19px; }
.results-heading span { color: var(--rp-text-3); font-size: 13px; }
.public-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px;
  margin-bottom: 10px;
  background: var(--rp-card);
  border: 1px solid var(--rp-border);
  border-radius: var(--rp-radius);
}
.search { flex: 1 1 180px; min-width: 0; }
.select, .sort { width: 118px; }
.type-seg, .view-toggle {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  border-radius: 10px;
  background: var(--surface-3);
}
.type-seg button, .view-toggle button {
  display: grid;
  place-items: center;
  min-height: 34px;
  padding: 0 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--rp-text-3);
  font-size: 13px;
  white-space: nowrap;
  cursor: pointer;
}
.type-seg button:hover, .view-toggle button:hover { color: var(--rp-text); }
.type-seg button.active, .view-toggle button.active {
  background: var(--rp-card);
  color: var(--rp-primary-dark);
  box-shadow: var(--shadow-xs);
}
.view-toggle button { min-width: 36px; padding: 0; }
.clear-filters {
  min-height: 36px;
  padding: 0 8px;
  border: 0;
  background: transparent;
  color: var(--rp-primary-dark);
  cursor: pointer;
}
@media (max-width: 860px) {
  .roadmap-stats { gap: 8px; margin: 12px 0 20px; }
  .roadmap-stat { padding: 10px; }
  .public-toolbar .search { flex-basis: 100%; }
}
@media (max-width: 620px) {
  .roadmap-mark { display: none; }
  .roadmap-stat dt { display: grid; gap: 4px; font-size: 12px; }
  .roadmap-stat dd { font-size: 21px; }
  .type-seg { flex: 1 1 100%; }
  .type-seg button { flex: 1; padding-inline: 2px; }
  .select, .sort { flex: 1 1 0; min-width: 0; }
}
</style>
