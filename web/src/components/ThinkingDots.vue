<template><span class="thinking" role="status"><span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>{{ label || '正在整理' }}</span></template>
<script setup lang="ts">
defineProps<{ label?: string }>();
</script>
<style scoped>
.thinking { display:inline-flex; gap:10px; align-items:center; color:var(--rp-text-3); font-size:13px; padding:12px 0; }.dots { display:flex; gap:4px; }.dots i { width:5px; height:5px; background:var(--rp-primary); border-radius:50%; animation:pulse 1s infinite alternate; }.dots i:nth-child(2){animation-delay:.2s}.dots i:nth-child(3){animation-delay:.4s}@keyframes pulse{to{opacity:.25;transform:translateY(-3px)}}@media(prefers-reduced-motion:reduce){.dots i{animation:none}}
</style>
