<template>
  <section class="contact-panel" aria-label="联系方式与需求通知">
    <h2>留下邮箱，方便一起完善需求</h2>
    <p>有需要确认的细节或进度更新时，我们可以通过邮件联系你。</p>
    <el-form-item label="联系邮箱（可选）">
      <el-input :model-value="email" @update:model-value="$emit('update:email', $event)" type="email" maxlength="255" placeholder="你的邮箱" autocomplete="email" />
    </el-form-item>
    <el-checkbox :model-value="optIn" @update:model-value="$emit('update:optIn', !!$event)">接收需求进度、发版和讨论邮件</el-checkbox>
    <small>邮箱仅用于联系，不会公开。勾选后需到邮箱确认订阅，可随时退订；也可以不留邮箱直接提交。</small>
  </section>
</template>

<script setup lang="ts">
defineProps<{ email: string; optIn: boolean }>()
defineEmits<{ 'update:email': [value: string]; 'update:optIn': [value: boolean] }>()
</script>

<style scoped>
.contact-panel { border:1px solid var(--rp-primary); background:var(--rp-primary-soft); padding:20px; border-radius:16px; margin:0 0 24px; }
h2 { font-size:17px; margin:0 0 8px; color:var(--rp-text); }
p { color:var(--rp-text-2); font-size:14px; line-height:1.6; margin:0 0 16px; }
small { display:block; color:var(--rp-text-2); line-height:1.6; margin-top:8px; }
.contact-panel :deep(.el-checkbox) { height:auto; white-space:normal; align-items:flex-start; }
.contact-panel :deep(.el-checkbox__label) { white-space:normal; line-height:1.5; }
</style>
