<template>
  <section class="intake-page">
    <header><div><h1>与 AI 讨论需求</h1><p>直接描述行影集遇到的问题或想法，AI 帮你整理成需求单。</p></div><el-button @click="router.push({ name: 'submit' })">填写表单</el-button></header>
    <el-alert type="info" :closable="false" title="只讨论行影集。AI 整理后会展示需求预览，点击确认才会正式提交。请勿输入密码或密钥。" />
    <div class="timeline" role="log" aria-label="提交前需求讨论" aria-live="polite">
      <p v-if="!messages.length">可以这样开始：行影集批量导出照片失败，希望能看到原因并重新导出。</p>
      <article v-for="(message, index) in messages" :key="index" :class="message.role">
        <strong>{{ message.role === 'user' ? '你' : '行影集 AI 助手' }}</strong>
        <div v-if="message.role === 'assistant'" class="response" v-html="renderConversationMarkdown(message.text)"></div><p v-else>{{ message.text }}</p>
      </article>
      <p v-if="sending" role="status">正在梳理需求…</p>
    </div>
    <form class="panel composer" @submit.prevent="send">
      <p v-if="quota" class="quota" role="status">今日已用 {{ quota.daily_used }}/{{ quota.daily_limit }} 次，剩余 {{ quota.daily_remaining }} 次 · 每 {{ quota.interval_seconds }} 秒最多发送一次（失败也计次）</p>
      <el-input v-model="content" type="textarea" :rows="3" maxlength="2000" show-word-limit aria-label="讨论内容" placeholder="描述行影集的问题、使用场景或希望改进的功能…" @keydown.ctrl.enter.prevent="send" />
      <div class="actions"><span>{{ cooldown > 0 ? `还需等待 ${cooldown} 秒` : '可继续补充，AI 会更新需求预览' }}</span><el-button type="primary" native-type="submit" :loading="sending" :disabled="!content.trim() || sending || submitting || cooldown > 0 || quota?.daily_remaining === 0">发送</el-button></div>
    </form>
    <section v-if="draft" class="panel preview" aria-label="AI 整理的需求单">
      <h2>AI 已整理好需求单</h2><p>请核对并修改下面的信息，确认后提交。</p>
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="需求类型"><el-select v-model="draft.type"><el-option label="问题修复" value="bug" /><el-option label="体验优化" value="improvement" /><el-option label="新功能" value="feature" /></el-select></el-form-item>
        <el-form-item label="需求标题" required><el-input v-model="draft.title" maxlength="160" /></el-form-item>
        <el-form-item label="需求描述" required><el-input v-model="draft.description" type="textarea" :rows="5" maxlength="4000" /></el-form-item>
        <el-form-item label="期望行为"><el-input v-model="draft.expected_behavior" type="textarea" maxlength="1000" /></el-form-item>
        <el-form-item label="复现步骤"><el-input v-model="draft.steps_to_reproduce" type="textarea" maxlength="1000" /></el-form-item>
        <RequirementContact v-model:email="email" v-model:opt-in="optIn" />
        <p>匿名需求公开展示；对话内容和联系邮箱不会随需求单公开。</p>
        <el-button native-type="submit" type="primary" :loading="submitting" :disabled="sending || submitted">确认并提交需求</el-button>
      </el-form>
    </section>
  </section>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, type Requirement } from '../../api'
import { intake, type Draft } from '../../api/intake'
import type { Quota } from '../../api/collaboration'
import { newEditToken, useAnonymousReceipts } from '../../stores/anonymousReceipts'
import { renderConversationMarkdown } from '../../conversationMarkdown'
import RequirementContact from '../../components/RequirementContact.vue'

const router = useRouter(), receipts = useAnonymousReceipts()
const content = ref(''), email = ref(''), optIn = ref(false), sending = ref(false), submitting = ref(false), submitted = ref(false)
const draft = ref<Draft | null>(null), quota = ref<Quota>(), cooldown = ref(0)
const messages = ref<{ role: string; text: string }[]>([])
let key = newEditToken(), state: string | undefined, creationKey = newEditToken()
let pendingSubmission: Record<string, unknown> | undefined
try {
  const saved = JSON.parse(sessionStorage.getItem('rp_intake') || 'null')
  if (saved?.key && saved?.state) { key = saved.key; state = saved.state; messages.value = saved.messages || []; draft.value = saved.draft; creationKey = saved.creationKey || creationKey }
} catch { /* The current tab also keeps a copy in memory. */ }
const timer = setInterval(() => { if (cooldown.value > 0) cooldown.value-- }, 1000)
function persist() {
  try { sessionStorage.setItem('rp_intake', JSON.stringify({ key, state, messages: messages.value, draft: draft.value, creationKey })) } catch { /* Continue in memory. */ }
}
function reason(e: any) { return e?.response?.data?.msg || '暂时无法连接，请稍后重试，也可以填写表单提交' }
async function send() {
  if (sending.value || submitting.value || cooldown.value || !content.value.trim()) return
  sending.value = true
  const text = content.value.trim()
  try {
    const result = await intake.send(key, text, state)
    messages.value.push({ role: 'user', text }, { role: 'assistant', text: result.reply })
    draft.value = result.draft; quota.value = result.quota; state = result.state; content.value = ''
    cooldown.value = (result.quota as Quota & { retry_after_seconds?: number }).retry_after_seconds || 0
    pendingSubmission = undefined; persist()
  } catch (e: any) {
    cooldown.value = Number(e?.response?.headers?.['retry-after']) || 0
    ElMessage.error(reason(e))
    try { quota.value = await intake.quota(key) } catch { /* Preserve prior quota on network failure. */ }
  } finally { sending.value = false }
}
async function submit() {
  if (!draft.value || sending.value || submitting.value || submitted.value) return
  if (draft.value.title.trim().length < 4 || draft.value.description.trim().length < 10) { ElMessage.error('请补充需求标题和描述'); return }
  if (optIn.value && !email.value.trim()) { ElMessage.error('请填写联系邮箱，或取消订阅'); return }
  submitting.value = true
  try {
    pendingSubmission ||= { ...draft.value, client_edit_token: creationKey, submitter_contact: email.value.trim(), notification_email: email.value.trim() || null, notification_opt_in: optIn.value }
    const created: Requirement = await api.createRequirement(pendingSubmission)
    if (created.edit_token && !receipts.save(created, created.edit_token)) ElMessage.warning('请在需求详情保存修改入口，以免丢失访问权限')
    submitted.value = true
    try { sessionStorage.removeItem('rp_intake') } catch { /* Submission already succeeded. */ }
    ElMessage.success(`感谢参与共创！REQ-${created.public_number} 已提交，可以继续讨论细节`)
    await router.push(`/requirements/REQ-${created.public_number}/conversation`)
  } catch (e) { ElMessage.error(reason(e)) } finally { submitting.value = false }
}
onMounted(async () => { try { quota.value = await intake.quota(key); cooldown.value = (quota.value as Quota & { retry_after_seconds?: number }).retry_after_seconds || 0 } catch (e) { ElMessage.error(reason(e)) } })
onBeforeUnmount(() => clearInterval(timer))
</script>

<style scoped>
.intake-page { max-width:880px; margin:auto; }
header { display:flex; justify-content:space-between; align-items:center; gap:16px; margin-bottom:20px; }
h1 { margin:0 0 8px; font-size:24px; }h2 { font-size:19px; }
p,.quota { color:var(--rp-text-2); line-height:1.7; }
.timeline { padding:20px 0; max-height:55vh; min-height:160px; overflow-y:auto; }
article { padding:16px; margin-bottom:16px; overflow-wrap:anywhere; }
article.user { background:var(--rp-primary-soft); border-radius:16px; margin-left:12%; }
article p { white-space:pre-wrap; }.response { line-height:1.8; }.response :deep(pre) { max-width:100%; overflow:auto; }
.composer { margin-bottom:24px; }.actions { display:flex; justify-content:space-between; gap:16px; align-items:center; margin-top:12px; }.actions span { font-size:13px; color:var(--rp-text-3); }
.preview { margin-bottom:24px; }.preview :deep(.el-select) { width:100%; }
@media(max-width:600px) { header { align-items:flex-start; }h1{font-size:20px}.timeline{max-height:45dvh}.actions span{max-width:65%} }
</style>
