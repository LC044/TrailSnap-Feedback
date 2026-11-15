<template>
  <details v-if="items.length" class="chat-activity" :open="active || undefined">
    <summary><span :class="{ pulse: active }" aria-hidden="true">{{ active ? '◌' : '✓' }}</span>{{ active ? items[items.length - 1]?.label : '查看处理过程' }}<small>{{ items.length }} 项活动</small></summary>
    <ol><li v-for="(item, i) in items" :key="i"><span aria-hidden="true">{{ item.status === 'completed' ? '✓' : item.status === 'failed' ? '!' : '·' }}</span>{{ item.label }}<small>{{ item.status === 'completed' ? '完成' : item.status === 'failed' ? '未完成' : active ? '进行中' : '已结束' }}</small></li></ol>
  </details>
</template>
<script setup lang="ts">
import type { ChatActivity } from '../api/chatStream'
defineProps<{ items: ChatActivity[]; active?: boolean }>()
</script>
<style scoped>
.chat-activity { margin:0 0 16px; color:var(--rp-text-2); font-size:12px; border:1px solid var(--rp-border); border-radius:12px; max-width:560px; background:var(--rp-bg); }summary { display:flex; align-items:center; gap:8px; padding:12px; cursor:pointer; list-style:none; }summary::-webkit-details-marker { display:none; }small { margin-left:auto; color:var(--rp-text-3); font-size:11px; }ol { list-style:none; margin:0; padding:0 12px 12px; }li { display:flex; align-items:center; gap:8px; padding:6px 0; }li > span,summary > span { color:var(--rp-primary); }.pulse { animation:activity-spin 1.6s linear infinite; }@keyframes activity-spin { to { transform:rotate(360deg); } }@media(prefers-reduced-motion:reduce) { .pulse { animation:none; } }
</style>
