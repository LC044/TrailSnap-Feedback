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
.contact-panel { border:1px solid var(--rp-border); background:var(--rp-primary-soft); padding:16px; border-radius:12px; margin:0 0 20px; }
h2 span { font-size:12px; font-weight:400; color:var(--rp-text-3); margin-left:8px; }
.contact-panel :deep(.el-form-item) { margin-bottom:10px; }
h2 { font-size:17px; margin:0 0 8px; color:var(--rp-text); }
p { color:var(--rp-text-2); font-size:14px; line-height:1.6; margin:0 0 16px; }
small { display:block; color:var(--rp-text-2); line-height:1.6; margin-top:8px; }
.contact-panel :deep(.el-checkbox) { height:auto; white-space:normal; align-items:flex-start; }
.contact-panel :deep(.el-checkbox__label) { white-space:normal; line-height:1.5; }
</style>
