<template>
  <section class="contact-panel" aria-label="联系方式与需求通知">
    <h2>邮件跟进 <span>可选 · 不公开</span></h2>
    <el-form-item label="联系邮箱（可选）">
      <el-input :model-value="email" @update:model-value="$emit('update:email', $event)" type="email" maxlength="255" placeholder="你的邮箱" autocomplete="email" />
    </el-form-item>
    <el-checkbox :model-value="optIn" @update:model-value="$emit('update:optIn', !!$event)">接收进度与讨论通知</el-checkbox>
    <small v-if="optIn">提交后到邮箱确认订阅，可随时退订。</small>
  </section>
</template>

<script setup lang="ts">
defineProps<{ email: string; optIn: boolean }>()
defineEmits<{ 'update:email': [value: string]; 'update:optIn': [value: boolean] }>()
</script>

<style scoped>
.contact-panel {
  position: relative;
  border: 1px solid var(--line);
  background: var(--surface-2);
  padding: 16px 18px;
  border-radius: 14px;
  margin: 0 0 20px;
  overflow: hidden;
}
.contact-panel::before {
  content: "";
  position: absolute; inset: 0 auto 0 0; width: 3px;
  background: linear-gradient(180deg, var(--primary), var(--brand-teal));
}
.contact-panel h2 { font-size: 13.5px; margin: 0 0 10px; color: var(--ink); }
.contact-panel h2 span { font-size: 11px; font-weight: 500; color: var(--ink-4); margin-left: 8px; }
.contact-panel :deep(.el-form-item) { margin-bottom: 10px; }
.contact-panel :deep(.el-checkbox) { height: auto; white-space: normal; align-items: flex-start; }
.contact-panel :deep(.el-checkbox__label) { white-space: normal; line-height: 1.5; font-size: 12.5px; }
small { display: block; color: var(--ink-4); font-size: 11.5px; line-height: 1.6; margin-top: 6px; }
</style>
