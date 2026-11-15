<template>
  <details v-if="quota" class="chat-quota">
    <summary aria-label="查看对话额度">
      <span v-if="quota.limit_mode !== 'tokens'">今日 {{ quota.daily_used }}/{{ quota.daily_limit }} 次</span>
      <span v-if="quota.limit_mode !== 'count' && quota.tokens_limit !== undefined">Token {{ compact(quota.tokens_used || 0) }}/{{ compact(quota.tokens_limit) }}</span>
      <span>间隔 {{ quota.interval_seconds }} 秒</span>
      <span v-if="quota.exhausted" class="exhausted">{{ quota.global_exhausted ? '服务今日额度已用完' : '今日个人额度已用完' }}</span>
    </summary>
    <p>每日重置；失败与重试也计次。Token 按完整输入与最大输出预留，包含历史，不代表实际账单。</p>
  </details>
</template>
<script setup lang="ts">
import type { Quota } from '../api/collaboration'
defineProps<{ quota?: Quota }>()
const compact = (value: number) => value.toLocaleString()
</script>
<style scoped>
.chat-quota { color:var(--rp-text-3); font-size:12px; margin:8px 0; }
summary { cursor:pointer; display:flex; flex-wrap:wrap; gap:6px 14px; min-height:28px; align-items:center; }
summary::after { content:'ⓘ'; }p { line-height:1.6; max-width:540px; margin:4px 0 10px; }
.exhausted{color:var(--rp-text-2)}
</style>
