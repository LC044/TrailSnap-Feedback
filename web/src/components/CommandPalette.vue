<template>
  <Teleport to="body">
    <Transition name="cmdk">
      <div v-if="open" class="cmdk-overlay" role="dialog" aria-modal="true" aria-label="命令面板" @mousedown.self="emit('close')">
        <div class="cmdk-panel" @keydown="onKeydown">
          <div class="cmdk-search">
            <el-icon :size="17"><Search /></el-icon>
            <input ref="inputEl" v-model="query" type="text" placeholder="搜索页面、需求编号或标题…"
              aria-label="搜索页面或需求" autocomplete="off" spellcheck="false" />
            <kbd @click="emit('close')">Esc</kbd>
          </div>

          <div ref="listEl" class="cmdk-list">
            <template v-for="group in groups" :key="group.label">
              <p v-if="group.rows.length" class="cmdk-group-label">{{ group.label }}</p>
              <button v-for="row in group.rows" :key="row.id" type="button" class="cmdk-row"
                :class="{ active: cursor === row.index }" @mousemove="cursor = row.index" @click="select(row)">
                <span class="cmdk-ico" :class="row.tone"><el-icon :size="15"><component :is="row.icon" /></el-icon></span>
                <span class="cmdk-copy">
                  <span class="cmdk-title" v-html="highlight(row.title)"></span>
                  <small v-if="row.meta">{{ row.meta }}</small>
                </span>
                <span v-if="row.tag" class="tag no-dot" :class="row.tagClass">{{ row.tag }}</span>
                <el-icon v-if="cursor === row.index" class="cmdk-enter" :size="13"><Right /></el-icon>
              </button>
            </template>
            <div v-if="!flat.length" class="cmdk-empty">
              <el-icon :size="26"><Search /></el-icon>
              <p>没有匹配的结果</p>
              <small>试试页面名称，或 REQ 编号</small>
            </div>
          </div>

          <div class="cmdk-foot">
            <span><kbd>↑</kbd><kbd>↓</kbd> 移动</span>
            <span><kbd>↵</kbd> 打开</span>
            <span class="cmdk-foot-hint">共 {{ flat.length }} 条结果</span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch, type Component } from 'vue'
import { Document, Right, Search } from '@element-plus/icons-vue'
import { statusLabel, typeLabel } from '../labels'
import type { Requirement } from '../api'
import type { AppTab } from '../router'

type Row = {
  id: string; index: number; title: string; meta?: string; icon: Component; tone: string
  tag?: string; tagClass?: string
  action: () => void
}

const props = defineProps<{
  open: boolean
  tabs: Array<{ key: AppTab; label: string; icon: Component }>
  requirements: Requirement[]
}>()
const emit = defineEmits<{ close: []; navigate: [tab: AppTab]; openRequirement: [number: number] }>()

const query = ref('')
const cursor = ref(0)
const inputEl = ref<HTMLInputElement | null>(null)
const listEl = ref<HTMLElement | null>(null)

watch(() => props.open, async open => {
  if (!open) return
  query.value = ''
  cursor.value = 0
  await nextTick()
  inputEl.value?.focus()
})

const q = computed(() => query.value.trim().toLowerCase())

const tabRows = computed(() => props.tabs
  .filter(item => !q.value || item.label.toLowerCase().includes(q.value) || item.key.includes(q.value))
  .map(item => ({
    id: `tab-${item.key}`, index: 0, title: item.label, meta: undefined as string | undefined,
    icon: item.icon, tone: 'primary', action: () => emit('navigate', item.key),
  })))

const reqRows = computed(() => {
  const list = q.value
    ? props.requirements.filter(item => `${item.public_number ?? ''} ${item.title} ${item.description}`.toLowerCase().includes(q.value))
    : [...props.requirements].sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  return list.slice(0, 7).map(item => ({
    id: `req-${item.id}`, index: 0,
    title: item.title,
    meta: `REQ-${item.public_number ?? '—'} · ${typeLabel(item.type)} · ${item.created_by_name || '用户'}`,
    icon: Document as Component,
    tone: item.type === 'bug' ? 'danger' : item.type === 'improvement' ? 'violet' : 'primary',
    tag: statusLabel(item.status), tagClass: `s-${item.status}`,
    action: () => { if (item.public_number) emit('openRequirement', item.public_number) },
  }))
})

const flat = computed<Row[]>(() => {
  const rows = [...reqRows.value, ...tabRows.value]
  rows.forEach((row, index) => { row.index = index })
  return rows
})
const groups = computed(() => {
  const tabs = flat.value.filter(row => row.id.startsWith('tab-'))
  const reqs = flat.value.filter(row => row.id.startsWith('req-'))
  return [
    { label: q.value ? '匹配的需求' : '最近更新', rows: reqs },
    { label: '页面', rows: tabs },
  ]
})

function highlight(text: string) {
  const needle = query.value.trim()
  if (!needle) return escapeHtml(text)
  const index = text.toLowerCase().indexOf(needle.toLowerCase())
  if (index < 0) return escapeHtml(text)
  const before = escapeHtml(text.slice(0, index))
  const hit = escapeHtml(text.slice(index, index + needle.length))
  const after = escapeHtml(text.slice(index + needle.length))
  return `${before}<mark>${hit}</mark>${after}`
}
function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]!))
}

function move(delta: number) {
  if (!flat.value.length) return
  cursor.value = (cursor.value + delta + flat.value.length) % flat.value.length
  nextTick(() => listEl.value?.querySelector('.cmdk-row.active')?.scrollIntoView({ block: 'nearest' }))
}
function select(row: Row) {
  row.action()
  emit('close')
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown') { event.preventDefault(); move(1) }
  else if (event.key === 'ArrowUp') { event.preventDefault(); move(-1) }
  else if (event.key === 'Enter') {
    event.preventDefault()
    const row = flat.value[cursor.value]
    if (row) select(row)
  } else if (event.key === 'Escape') { event.preventDefault(); emit('close') }
}
</script>

<style scoped>
.cmdk-overlay {
  position: fixed; inset: 0; z-index: 3000;
  display: flex; align-items: flex-start; justify-content: center;
  padding: min(16vh, 140px) 16px 24px;
  background: color-mix(in srgb, var(--ink) 38%, transparent);
  backdrop-filter: blur(6px);
}
.cmdk-panel {
  width: min(100%, 620px);
  display: flex; flex-direction: column;
  max-height: 68vh;
  border: 1px solid var(--line);
  border-radius: 20px;
  background: var(--surface);
  box-shadow: 0 40px 90px -40px rgba(8, 12, 30, .7);
  overflow: hidden;
}
.cmdk-search { display: flex; align-items: center; gap: 10px; padding: 14px 16px; border-bottom: 1px solid var(--line); }
.cmdk-search > .el-icon { color: var(--ink-4); }
.cmdk-search input {
  flex: 1; min-width: 0; border: 0; background: transparent; outline: none;
  font-size: 15px; color: var(--ink); padding: 4px 0;
}
.cmdk-search input::placeholder { color: var(--ink-4); }
.cmdk-search kbd { cursor: pointer; }

.cmdk-list { flex: 1; min-height: 0; overflow-y: auto; padding: 8px; }
.cmdk-group-label {
  margin: 10px 10px 6px;
  color: var(--ink-4); font-size: 10px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase;
}
.cmdk-row {
  display: flex; align-items: center; gap: 11px; width: 100%;
  padding: 9px 10px; border: 0; border-radius: 11px;
  background: transparent; text-align: left; cursor: pointer; color: var(--ink-2);
}
.cmdk-row.active { background: var(--primary-soft); color: var(--ink); }
.cmdk-ico {
  display: grid; place-items: center; flex: none;
  width: 30px; height: 30px; border-radius: 9px;
  background: var(--surface-3); color: var(--ink-3);
}
.cmdk-ico.primary { background: var(--primary-soft); color: var(--primary); }
.cmdk-ico.violet { background: var(--violet-soft); color: var(--violet); }
.cmdk-ico.danger { background: var(--danger-soft); color: var(--danger); }
.cmdk-copy { display: grid; min-width: 0; flex: 1; line-height: 1.35; }
.cmdk-title { font-size: 13.5px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cmdk-title :deep(mark) { background: color-mix(in srgb, var(--accent) 34%, transparent); color: inherit; border-radius: 3px; padding: 0 1px; }
.cmdk-copy small { color: var(--ink-4); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cmdk-enter { color: var(--primary); flex: none; }
.cmdk-empty { display: grid; place-items: center; gap: 6px; padding: 42px 16px; color: var(--ink-4); text-align: center; }
.cmdk-empty p { color: var(--ink-2); font-size: 14px; margin: 0; }
.cmdk-empty small { font-size: 12px; }
.cmdk-foot {
  display: flex; align-items: center; gap: 14px;
  padding: 10px 16px; border-top: 1px solid var(--line);
  background: var(--surface-2); color: var(--ink-4); font-size: 11px;
}
.cmdk-foot span { display: inline-flex; align-items: center; gap: 4px; }
.cmdk-foot-hint { margin-left: auto; }

.cmdk-enter-active, .cmdk-leave-active { transition: opacity .2s var(--ease); }
.cmdk-enter-active .cmdk-panel { animation: pop .24s var(--ease-out) both; }
.cmdk-enter-from, .cmdk-leave-to { opacity: 0; }

@media (max-width: 640px) {
  .cmdk-overlay { padding: 0; align-items: stretch; }
  .cmdk-panel { max-height: 100dvh; height: 100dvh; border-radius: 0; border: 0; }
  .cmdk-search { padding: 16px; }
}
</style>