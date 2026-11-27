<template>
  <div class="panel flush table-panel" :class="{ 'board-mode': view === 'board' }">
    <!-- ================= 列表视图 ================= -->
    <template v-if="view !== 'board'">
      <div v-if="loading && !items.length" class="req-list sk-list" aria-busy="true" aria-label="正在加载需求">
        <div v-for="n in 6" :key="n" class="req-row sk-row">
          <span class="sk sk-type"></span>
          <div class="req-main" style="gap:8px">
            <span class="sk sk-line w70"></span>
            <span class="sk sk-line w45"></span>
            <span class="sk sk-line w30"></span>
          </div>
          <span class="sk sk-pill"></span>
        </div>
      </div>
      <div v-else-if="items.length" class="req-list">
        <article v-for="(item, index) in pagedItems" :key="item.id" class="req-row" tabindex="0" role="link"
          :aria-label="`REQ-${item.public_number} ${item.title}，${statusLabel(item.status)}`"
          :style="{ animationDelay: `${Math.min(index, 10) * 24}ms` }"
          @click="emit('open', item)" @keydown.enter.self.prevent="emit('open', item)">
          <span class="req-type-icon" :class="`t-${item.type}`">
            <el-icon :size="19"><component :is="typeIcon(item.type)" /></el-icon>
          </span>

          <div class="req-main">
            <button class="req-title" type="button" @click.stop="emit('open', item)">
              <span class="req-number">REQ-{{ item.public_number }}</span>
              <span>{{ item.title }}</span>
            </button>
            <p class="req-desc">{{ item.description }}</p>
            <div class="req-meta">
              <span class="tag" :class="`s-${stageKeyOf(item.status)}`" :title="statusLabel(item.status)">{{ stageLabel(item.status) }}</span>
              <span class="trail" :title="trailTitle(item.status)" :aria-label="trailTitle(item.status)" role="img">
                <i v-for="(stage, stageIndex) in trailStages" :key="stage.key" class="trail-seg"
                  :class="{
                    done: trailOf(item.status).index > stageIndex,
                    now: trailOf(item.status).index === stageIndex,
                    off: trailOf(item.status).stopped,
                  }"></i>
              </span>
              <span v-if="item.priority && item.priority !== 'normal'" class="tag no-dot" :class="`p-${item.priority}`">{{ priorityLabel(item.priority) }}</span>
              <span class="req-person">
                <span class="avatar" :style="{ ...avatarColor(creatorName(item)), width: '20px', height: '20px', fontSize: '10px', boxShadow: 'none' }">{{ creatorName(item).slice(0, 1) }}</span>
                {{ creatorName(item) }}
              </span>
              <span v-if="item.follower_count" class="req-person"><el-icon :size="12"><Star /></el-icon>{{ item.follower_count }}</span>
            </div>
          </div>

          <div class="req-side">
            <span class="req-when">{{ relativeTime(item.updated_at) }}</span>
            <div class="req-actions" @click.stop>
              <el-dropdown trigger="click" @command="(command: string) => emit('action', { item, command })">
                <button class="icon-btn" type="button" :aria-label="`更多操作：${item.title}`" style="width:30px;height:30px">
                  <el-icon :size="15"><MoreFilled /></el-icon>
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="follow">关注（{{ item.follower_count || 0 }}）</el-dropdown-item>
                    <el-dropdown-item v-if="canWithdraw(item)" command="withdraw">撤回</el-dropdown-item>
                    <el-dropdown-item v-if="manager" command="review">审核</el-dropdown-item>
                    <el-dropdown-item v-if="manager" command="edit">编辑需求</el-dropdown-item>
                    <el-dropdown-item v-if="manager" command="status">修改状态</el-dropdown-item>
                    <el-dropdown-item v-if="manager && !item.github_issue_number" command="github-create">新建 GitHub Issue</el-dropdown-item>
                    <el-dropdown-item v-if="manager && !item.github_issue_number" command="github-link">关联已有 GitHub Issue</el-dropdown-item>
                    <el-dropdown-item v-if="manager && item.github_issue_number && item.github_state !== 'closed'" command="github-close">关闭 GitHub Issue 与需求</el-dropdown-item>
                    <el-dropdown-item v-if="manager && item.github_issue_number" command="github-unlink">取消 Issue 关联</el-dropdown-item>
                    <el-dropdown-item v-if="manager && item.status !== 'closed'" command="close">关闭需求</el-dropdown-item>
                    <el-dropdown-item v-if="manager" divided command="delete">删除需求</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </article>
      </div>

      <div v-else class="empty">
        <span class="req-type-icon"><el-icon :size="22"><Collection /></el-icon></span>
        <strong>暂无匹配需求</strong>
        <span>试试其他关键词或筛选条件。</span>
      </div>

      <div v-if="items.length" class="table-foot">
        <span class="total">
          共 <strong>{{ items.length }}</strong> 条需求
          <template v-if="items.length > pageSize"> · 第 {{ page }} / {{ pageCount }} 页</template>
        </span>
        <el-pagination v-if="items.length > pageSize" layout="prev, pager, next" :total="items.length"
          :page-size="pageSize" :current-page="page" @current-change="page = $event" />
      </div>
    </template>

    <!-- ================= 看板视图 ================= -->
    <div v-else-if="loading && !items.length" class="empty" aria-busy="true">
      <span>正在加载需求…</span>
    </div>
    <div v-else class="board">
      <section v-for="column in boardColumns" :key="column.key" class="board-col">
        <header class="board-col-head">
          <i :style="{ background: column.color }"></i>
          <strong>{{ column.label }}</strong>
          <span>{{ grouped[column.key]?.length ?? 0 }}</span>
        </header>
        <button v-for="item in grouped[column.key]" :key="item.id" type="button" class="board-card"
          :aria-label="`REQ-${item.public_number} ${item.title}`" @click="emit('open', item)">
          <div class="bc-top">
            <span class="req-number">REQ-{{ item.public_number }}</span>
            <span class="tag no-dot" :class="`t-${item.type}`">{{ typeLabel(item.type) }}</span>
          </div>
          <p class="bc-title">{{ item.title }}</p>
          <div class="bc-foot">
            <span class="req-person">
              <span class="avatar" :style="{ ...avatarColor(creatorName(item)), width: '18px', height: '18px', fontSize: '9px', boxShadow: 'none' }">{{ creatorName(item).slice(0, 1) }}</span>
              {{ creatorName(item) }}
            </span>
            <span class="req-when">{{ relativeTime(item.updated_at) }}</span>
          </div>
        </button>
        <p v-if="!grouped[column.key]?.length" class="board-empty">暂无需求</p>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Collection, MoreFilled, Opportunity, FirstAidKit, MagicStick, Star } from '@element-plus/icons-vue'
import type { Requirement } from './api'
import { avatarColor, parseServerDate, priorityLabel, statusLabel, typeLabel } from './labels'
import { stageKeyOf, stageLabel } from './stages'
import { boardColumns, boardColumnOf, trailOf, trailStages } from './requirementTrail'

const props = defineProps<{
  items: Requirement[]
  manager?: boolean
  user?: { id: string } | null
  view?: 'list' | 'board'
  loading?: boolean
}>()
const emit = defineEmits<{ open: [item: Requirement]; action: [payload: { item: Requirement; command: string }] }>()

/* 每页条数随视口高度自适应：高分屏多展示几行，避免底部大片空白。 */
const pageSize = ref(8)
const syncPageSize = () => {
  pageSize.value = Math.min(50, Math.max(8, Math.floor((window.innerHeight - 400) / 82)))
}
onMounted(() => { syncPageSize(); window.addEventListener('resize', syncPageSize) })
onBeforeUnmount(() => window.removeEventListener('resize', syncPageSize))
const page = ref(1)
watch(() => props.items, () => { page.value = 1 })
watch(pageSize, () => { page.value = Math.min(page.value, Math.max(1, Math.ceil(props.items.length / pageSize.value))) })
const pagedItems = computed(() => props.items.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const pageCount = computed(() => Math.max(1, Math.ceil(props.items.length / pageSize.value)))

const typeIcons = { feature: Opportunity, improvement: MagicStick, bug: FirstAidKit }
const typeIcon = (type: string) => (typeIcons as Record<string, typeof Star>)[type] ?? MagicStick

const grouped = computed(() => {
  const map: Record<string, Requirement[]> = {}
  for (const column of boardColumns) map[column.key] = []
  for (const item of props.items) map[boardColumnOf(item.status)]?.push(item)
  return map
})

const creatorName = (item: Requirement) => item.created_by_name || '用户'
const canWithdraw = (item: Requirement) =>
  !!props.user && item.created_by === props.user.id && !['scheduled', 'developing', 'testing', 'release_ready', 'released'].includes(item.status)

const trailTitle = (status: string) => {
  const state = trailOf(status)
  return state.stopped ? `当前：${statusLabel(status)}` : `当前阶段：${state.stage?.label ?? '—'}`
}

const rtf = new Intl.RelativeTimeFormat('zh-CN', { numeric: 'auto' })
function relativeTime(value: string) {
  const date = parseServerDate(value)
  if (Number.isNaN(date.getTime())) return value
  const diff = (date.getTime() - Date.now()) / 1000
  const abs = Math.abs(diff)
  if (abs < 60) return '刚刚'
  if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour')
  if (abs < 86400 * 30) return rtf.format(Math.round(diff / 86400), 'day')
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit' })
    .format(date).replace(/\//g, '-')
}
</script>

<style scoped>
.table-panel { display: flex; flex-direction: column; }
.req-row { animation: rise .4s var(--ease-out) both; }
.table-foot {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 12px 18px; border-top: 1px solid var(--line);
  background: color-mix(in srgb, var(--surface-2) 60%, transparent);
}
.table-foot .total { color: var(--ink-3); font-size: 12.5px; }
.table-foot .total strong { color: var(--ink); font-variant-numeric: tabular-nums; }
.empty span { max-width: 360px; font-size: 12.5px; line-height: 1.6; }

@media (max-width: 860px) {
  .table-foot { padding: 10px 14px; }
  .req-side { flex-wrap: wrap; }
  .req-actions { margin-left: auto; }
}
</style>