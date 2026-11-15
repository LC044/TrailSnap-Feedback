<template>
  <section class="intake-page">
    <header><div><h1>与 AI 讨论需求</h1><p>说说你的想法，需求单交给 AI 整理。</p></div><el-button @click="router.push({ name: 'submit' })">填写表单</el-button></header>
    <ol class="flow" aria-label="提交步骤"><li class="active">1 描述想法</li><li :class="{ active: !!draft }">2 整理需求</li><li>3 确认提交</li></ol>
    <div class="intake-workspace"><div class="chat-area">
    <div ref="timeline" class="timeline" role="log" aria-label="提交前需求讨论" aria-live="polite">
      <div v-if="!messages.length" class="welcome"><span class="welcome-mark" aria-hidden="true">✦</span><h2>哪里可以更好？</h2><div class="starter-options"><button v-for="sample in samples" :key="sample" type="button" @click="content = sample">{{ sample }}</button></div></div>
      <article v-for="(message, index) in messages" :key="index" :class="message.role">
        <strong>{{ message.role === 'user' ? '你' : '行影集 AI 助手' }}</strong>
        <div v-if="message.role === 'assistant'" class="response" v-html="renderConversationMarkdown(message.text)"></div><p v-else>{{ message.text }}</p>
      </article>
      <article v-if="sending" class="assistant"><ThinkingDots /></article>
    </div>
    <form class="panel composer" @submit.prevent="send">
      <ChatQuota :quota="quota" />
      <el-input v-model="content" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" resize="none" maxlength="2000" show-word-limit aria-label="讨论内容" placeholder="描述问题，或回答 AI 的提问…" @keydown.ctrl.enter.prevent="send" @keydown.meta.enter.prevent="send" />
      <div class="actions"><span>{{ cooldown > 0 ? `还需等待 ${cooldown} 秒` : '仅讨论行影集' }}</span><el-button type="primary" native-type="submit" :loading="sending" :disabled="!content.trim() || sending || submitting || cooldown > 0 || quota?.exhausted">发送</el-button></div>
    </form>
    <button v-if="draft" class="mobile-preview-toggle" type="button" :aria-expanded="showPreview" @click="showPreview = !showPreview">{{ showPreview ? '收起需求单 ↑' : '查看需求单 · 确认提交 →' }}</button>
    </div>
    <section v-if="draft" class="panel preview" :class="{ expanded: showPreview }" aria-label="AI 整理的需求单">
      <div class="preview-title"><h2>需求单</h2><span class="draft-status" role="status">已更新 · 待确认</span></div>
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="需求类型"><el-select v-model="draft.type"><el-option label="问题修复" value="bug" /><el-option label="体验优化" value="improvement" /><el-option label="新功能" value="feature" /></el-select></el-form-item>
        <el-form-item label="需求标题" required><el-input v-model="draft.title" maxlength="160" /></el-form-item>
        <el-form-item label="需求描述" required><el-input v-model="draft.description" type="textarea" :rows="5" maxlength="4000" /></el-form-item>
        <el-form-item label="期望行为"><el-input v-model="draft.expected_behavior" type="textarea" maxlength="1000" /></el-form-item>
        <el-form-item label="复现步骤"><el-input v-model="draft.steps_to_reproduce" type="textarea" maxlength="1000" /></el-form-item>
        <RequirementContact v-model:email="email" v-model:opt-in="optIn" />
        <p class="privacy-note">需求单公开，邮箱与对话保密。</p>
        <el-button native-type="submit" type="primary" :loading="submitting" :disabled="sending || submitted">确认并提交需求</el-button>
      </el-form>
    </section></div>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, type Requirement } from '../../api'
import { intake, type Draft } from '../../api/intake'
import type { Quota } from '../../api/collaboration'
import { newEditToken, useAnonymousReceipts } from '../../stores/anonymousReceipts'
import { renderConversationMarkdown } from '../../conversationMarkdown'
import RequirementContact from '../../components/RequirementContact.vue'
import ChatQuota from '../../components/ChatQuota.vue'
import ThinkingDots from '../../components/ThinkingDots.vue'

const router = useRouter(), receipts = useAnonymousReceipts()
const content = ref(''), email = ref(''), optIn = ref(false), sending = ref(false), submitting = ref(false), submitted = ref(false)
const draft = ref<Draft | null>(null), quota = ref<Quota>(), cooldown = ref(0)
const messages = ref<{ role: string; text: string }[]>([])
const samples = ['行影集照片导出失败', '想改进人物相册', '行影集地图轨迹有问题']
const timeline = ref<HTMLElement | null>(null), showPreview = ref(false)
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
async function scrollToEnd() { await nextTick(); if (timeline.value) timeline.value.scrollTop = timeline.value.scrollHeight }
async function send() {
  if (sending.value || submitting.value || cooldown.value || !content.value.trim()) return
  sending.value = true
  const text = content.value.trim()
  messages.value.push({ role: 'user', text })
  await scrollToEnd()
  try {
    const result = await intake.send(key, text, state)
    messages.value.push({ role: 'assistant', text: result.reply })
    draft.value = result.draft; quota.value = result.quota; state = result.state; content.value = ''
    cooldown.value = (result.quota as Quota & { retry_after_seconds?: number }).retry_after_seconds || 0
    pendingSubmission = undefined; persist()
  } catch (e: any) {
    messages.value.pop()
    cooldown.value = Number(e?.response?.headers?.['retry-after']) || 0
    ElMessage.error(reason(e))
    try { quota.value = await intake.quota(key) } catch { /* Preserve prior quota on network failure. */ }
  } finally { sending.value = false; await scrollToEnd() }
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
.intake-page { max-width:1200px; }
.intake-workspace { display:grid; grid-template-columns:minmax(0,1fr); gap:24px; align-items:start; }
.intake-workspace:has(.preview) { grid-template-columns:minmax(0,1.25fr) minmax(320px,.85fr); }
.chat-area { min-width:0; position:sticky; top:24px; }
.flow { display:flex; padding:0; gap:24px; list-style:none; font-size:12px; color:var(--rp-text-3); margin:0 0 20px; }.flow .active{color:var(--rp-primary)}
.timeline { height:clamp(260px,48dvh,580px); max-height:none; border-top:1px solid var(--rp-border); padding:12px 0; scrollbar-width:thin; scroll-behavior:smooth; }
.timeline article { margin-bottom:8px; padding:12px; animation:arrive .18s ease-out; }.timeline article strong{font-size:12px;color:var(--rp-text-3)}.timeline article p{margin:8px 0;line-height:1.65;color:var(--rp-text)}
.response { font-size:14px;line-height:1.75; }.response :deep(p){margin:8px 0;}
.welcome { display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; gap:16px; }.welcome h2{margin:0}.welcome-mark{font-size:32px;color:var(--rp-primary)}.starter-options{display:flex;gap:8px;flex-wrap:wrap;justify-content:center}.starter-options button{border:1px solid var(--rp-border);background:var(--rp-card);color:var(--rp-text-2);border-radius:20px;padding:10px 14px;cursor:pointer;min-height:44px}.starter-options button:hover{border-color:var(--rp-primary);color:var(--rp-primary)}
.composer { padding:12px 16px; border-radius:18px; margin-bottom:12px; }.composer :deep(.el-textarea__inner){box-shadow:none;background:transparent;padding:8px 0;font-size:15px;}.actions{margin-top:8px;min-height:44px}.actions .el-button{min-width:72px;min-height:44px}.actions span{font-size:12px}
.preview { padding:20px; }.preview-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;gap:8px}.preview-title h2{margin:0}.draft-status{font-size:12px;color:var(--rp-primary)}.privacy-note{font-size:12px}.preview :deep(.el-form-item){margin-bottom:16px}.preview :deep(.el-button[type=submit]){width:100%;min-height:44px}.mobile-preview-toggle{display:none}
@keyframes arrive{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
@media(max-width:1000px){.intake-workspace:has(.preview){grid-template-columns:1fr}.chat-area{position:static}.mobile-preview-toggle{display:block;width:100%;min-height:48px;border:1px solid var(--rp-primary);background:var(--rp-primary-soft);color:var(--rp-primary);border-radius:12px;cursor:pointer}.preview{display:none}.preview.expanded{display:block}.timeline{height:clamp(240px,42dvh,480px)}header{margin-bottom:12px}header p{font-size:13px;margin-bottom:0}.flow{gap:20px;margin-bottom:14px}.composer{padding:10px 12px}article.user{margin-left:6%}}
@media(prefers-reduced-motion:reduce){.timeline article{animation:none}.timeline{scroll-behavior:auto}}
</style>
