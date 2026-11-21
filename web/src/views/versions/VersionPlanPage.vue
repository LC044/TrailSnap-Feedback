<template>
  <section class="versions-page">
    <div class="page-head">
      <div class="page-head-left">
        <div class="page-head-icon"><el-icon :size="23"><Flag /></el-icon></div>
        <div>
          <h1>版本计划</h1>
          <p class="sub">人工挑选进入版本的需求，跟踪每个版本的交付进度。</p>
          <p class="desc">锁定范围后生成快照，后续变更都需要记录原因。</p>
        </div>
      </div>
      <div class="page-head-actions">
        <el-button v-if="manager" type="primary" :icon="Plus" @click="$emit('create')">创建版本批次</el-button>
      </div>
    </div>

    <div v-if="!batches.length" class="panel empty">
      <svg width="72" height="72" viewBox="0 0 72 72" fill="none" aria-hidden="true">
        <path d="M14 54V26l22-12 22 12v28" stroke="var(--line-2)" stroke-width="1.5" stroke-linejoin="round" />
        <path d="M24 54V34l12-7 12 7v20" stroke="var(--primary)" stroke-width="1.5" stroke-linejoin="round" opacity=".55" />
      </svg>
      <strong>还没有版本批次</strong>
      <span>创建一个版本，把候选需求规划进同一个发布节奏。</span>
    </div>

    <div v-else class="batch-grid">
      <article v-for="batch in batches" :key="batch.id" class="panel batch-card">
        <header class="batch-top">
          <span class="batch-version">{{ batch.version_name }}</span>
          <span class="tag" :class="`s-${batch.status}`">{{ statusLabel(batch.status) }}</span>
        </header>

        <h2 class="batch-name">{{ batch.name }}</h2>
        <div class="batch-meta">
          <span class="chip">{{ batchTypeLabel(batch.batch_type) }}</span>
          <span v-if="batch.target_date" class="chip"><el-icon :size="12"><Calendar /></el-icon>{{ batch.target_date }}</span>
          <a v-if="batch.github_milestone_url" class="github-link" :href="batch.github_milestone_url" target="_blank" rel="noopener">
            <el-icon :size="12"><Link /></el-icon>Milestone #{{ batch.github_milestone_number }}
          </a>
        </div>
        <p class="batch-goal">{{ batch.goal }}</p>

        <div class="batch-progress">
          <div class="bp-head">
            <span>交付进度</span>
            <strong class="numeric">{{ completedCount(batch) }}<i>/</i>{{ batch.items.length }}</strong>
          </div>
          <div class="bp-track"><i :style="{ width: `${progressOf(batch)}%` }"></i></div>
        </div>

        <ul class="batch-items">
          <li v-for="item in batch.items" :key="item.id">
            <span class="delivery-dot" :class="`d-${item.delivery_status}`"></span>
            <div class="bi-copy">
              <strong>{{ item.requirement_snapshot.title }}</strong>
              <div class="bi-row">
                <template v-if="manager && !['planning','candidate_selection','published','completed','cancelled'].includes(batch.status)">
                  <el-select :model-value="item.delivery_status" size="small" class="bi-select" @change="$emit('update-delivery', batch.id, item.id, String($event))">
                    <el-option v-for="status in deliveryStatuses" :key="status" :label="deliveryLabel(status)" :value="status" />
                  </el-select>
                </template>
                <span v-else class="tag no-dot" :class="`d-${item.delivery_status}`">{{ deliveryLabel(item.delivery_status) }}</span>
                <el-button v-if="manager && ['planning','candidate_selection'].includes(batch.status)" size="small" text type="danger" @click="$emit('remove', batch.id, item.id)">移出</el-button>
              </div>
            </div>
          </li>
          <li v-if="!batch.items.length" class="batch-empty">还没有需求，先添加候选需求。</li>
        </ul>

        <div v-if="manager" class="batch-actions">
          <el-select v-if="['planning','candidate_selection'].includes(batch.status)" v-model="candidateSelection[batch.id]" filterable placeholder="选择候选需求" class="bi-candidate">
            <el-option v-for="requirement in candidates" :key="requirement.id" :label="requirement.title" :value="requirement.id" />
          </el-select>
          <el-button v-if="['planning','candidate_selection'].includes(batch.status)" @click="$emit('add', batch.id)">加入</el-button>
          <el-button v-if="batch.items.length && ['planning','candidate_selection'].includes(batch.status)" type="primary" @click="$emit('lock', batch.id)">锁定范围</el-button>
          <el-dropdown v-if="allowedStatuses(batch.status).length" @command="$emit('update-state', batch.id, String($event))">
            <el-button>更新状态<el-icon class="el-icon--right" :size="12"><ArrowDown /></el-icon></el-button>
            <template #dropdown>
              <el-dropdown-menu><el-dropdown-item v-for="status in allowedStatuses(batch.status)" :key="status" :command="status">{{ statusLabel(status) }}</el-dropdown-item></el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button text :icon="EditPen" class="batch-edit" @click="$emit('edit', batch)">编辑</el-button>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ArrowDown, Calendar, EditPen, Flag, Link, Plus } from '@element-plus/icons-vue'
import type { Batch, Requirement } from '../../api'
import { batchTypeLabel, deliveryLabel, statusLabel } from '../../labels'

defineProps<{ batches: Batch[]; candidates: Requirement[]; manager: boolean; candidateSelection: Record<string, string>; deliveryStatuses: string[]; allowedStatuses: (status: string) => string[] }>()
defineEmits<{
  create: []; edit: [batch: Batch]; add: [batchId: string]; remove: [batchId: string, itemId: string]
  lock: [batchId: string]; 'update-state': [batchId: string, status: string]
  'update-delivery': [batchId: string, itemId: string, status: string]
}>()

const completedCount = (batch: Batch) => batch.items.filter(item => item.delivery_status === 'completed').length
const progressOf = (batch: Batch) => batch.items.length ? (completedCount(batch) / batch.items.length) * 100 : 0
</script>

<style scoped>
.versions-page { min-width: 0; }
.batch-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(400px, 1fr)); gap: 16px; align-items: start; }
.batch-card {
  position: relative; display: flex; flex-direction: column;
  padding: 20px 20px 16px; margin-bottom: 0;
  transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}
.batch-card:hover { border-color: color-mix(in srgb, var(--primary) 22%, var(--line)); box-shadow: var(--shadow-md); }
.batch-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
.batch-version {
  display: inline-flex; align-items: center;
  padding: 3px 9px; border-radius: 7px;
  background: var(--surface-3); color: var(--ink-2);
  font-family: "SFMono-Regular", ui-monospace, Consolas, monospace;
  font-size: 11.5px; font-weight: 650; letter-spacing: -.01em;
}
.batch-name { margin: 0 0 8px; font-size: 16px; font-weight: 700; letter-spacing: -.015em; overflow-wrap: anywhere; }
.batch-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-bottom: 10px; }
.batch-goal {
  margin: 0 0 16px; color: var(--ink-2); font-size: 12.5px; line-height: 1.65;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.batch-progress { margin-bottom: 14px; }
.bp-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 6px; font-size: 11.5px; color: var(--ink-3); }
.bp-head strong { font-size: 13px; color: var(--ink); font-weight: 700; }
.bp-head i { font-style: normal; color: var(--ink-4); font-weight: 500; }
.bp-track { height: 6px; border-radius: 99px; background: var(--surface-3); overflow: hidden; }
.bp-track i { display: block; height: 100%; border-radius: 99px; background: linear-gradient(90deg, var(--primary), var(--brand-teal)); transition: width .6s var(--ease); }

.batch-items { list-style: none; margin: 0 0 14px; padding: 0; display: grid; gap: 6px; }
.batch-items li {
  display: flex; gap: 9px; align-items: flex-start;
  padding: 9px 11px; border-radius: 10px;
  background: var(--surface-2); border: 1px solid color-mix(in srgb, var(--line) 70%, transparent);
}
.batch-items li.batch-empty { display: block; color: var(--ink-4); font-size: 12px; text-align: center; padding: 14px; }
.delivery-dot { width: 7px; height: 7px; border-radius: 50%; margin-top: 6px; flex: none; background: var(--ink-5); }
.delivery-dot.d-developing { background: var(--primary); box-shadow: 0 0 0 3px var(--primary-soft); }
.delivery-dot.d-pr_open { background: var(--cyan); }
.delivery-dot.d-testing { background: var(--accent); }
.delivery-dot.d-completed { background: var(--success); }
.delivery-dot.d-blocked, .delivery-dot.d-removed { background: var(--danger); }
.bi-copy { min-width: 0; flex: 1; display: grid; gap: 5px; }
.bi-copy strong { font-size: 12.5px; font-weight: 600; line-height: 1.45; overflow-wrap: anywhere; color: var(--ink); }
.bi-row { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.bi-select { width: 132px; }
.bi-select :deep(.el-select__wrapper) { min-height: 26px; font-size: 11.5px; }
.batch-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: auto; padding-top: 12px; border-top: 1px solid var(--line); }
.bi-candidate { flex: 1 1 180px; min-width: 150px; }
.batch-actions .el-button { margin-left: 0; }
.batch-edit { margin-left: auto !important; }

@media (max-width: 720px) {
  .batch-grid { grid-template-columns: minmax(0, 1fr); }
  .batch-card { padding: 16px; }
  .batch-actions { display: grid; grid-template-columns: 1fr 1fr; }
  .batch-actions .bi-candidate { grid-column: 1 / -1; }
  .batch-actions .batch-edit { grid-column: 1 / -1; justify-self: start; margin-left: 0 !important; }
}
</style>