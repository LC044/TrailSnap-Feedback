<template>
  <div class="seg mode-tabs" role="group" aria-label="讨论类型">
    <button
      v-for="item in modes" :key="item.value" type="button"
      :class="{ active: modelValue === item.value }"
      :aria-pressed="modelValue === item.value"
      :disabled="disabled"
      @click="emit('update:modelValue', item.value)">{{ item.label }}</button>
  </div>
</template>
<script setup lang="ts">
import type { ChatMode } from '../api/intake'
defineProps<{ modes: { value: ChatMode; label: string }[]; modelValue: ChatMode; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [ChatMode] }>()
</script>
<style scoped>
.mode-tabs { flex: none; background: var(--surface-2); }
.mode-tabs button { min-height: 32px; padding: 0 12px; }
.mode-tabs button.active {
  background: color-mix(in srgb, var(--primary) 16%, var(--surface)); color: var(--primary-deep);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary) 32%, transparent);
}
@media (max-width: 600px) {
  .mode-tabs { flex: 1; min-width: 0; }
  .mode-tabs button { flex: 1; padding: 0 8px; font-size: 12px; }
}
</style>
