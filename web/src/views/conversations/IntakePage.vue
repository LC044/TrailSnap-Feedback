<template>
  <section class="intake-page">
    <header><div><h1>行影集 AI 助手</h1><p>反馈想法、排查问题，或了解使用方法。</p></div><div class="header-actions"><el-button v-if="draft" @click="showPreview = !showPreview">需求单 <span aria-hidden="true">↗</span></el-button><el-button @click="router.push({ name: 'submit' })">填写表单</el-button></div></header>
    <div class="mode-tabs" role="group" aria-label="讨论类型"><button v-for="item in modes" :key="item.value" type="button" :aria-pressed="mode === item.value" :disabled="sending" @click="mode = item.value">{{ item.label }}</button></div>
    <div class="knowledge-status" role="status"><span class="status-dot" :class="{ ready: snapshot?.ready }"></span><span>{{ snapshot?.ready ? `基于 ${snapshot.tag} 源码与官网文档` : snapshot?.message || '正在读取资料状态…' }}</span><small v-if="snapshot?.stale">资料更新中，当前使用缓存</small><small v-if="snapshot?.warning">{{ snapshot.warning }}</small></div>
    <div class="intake-workspace" :class="{ 'preview-open': draft && showPreview }"><div class="chat-area">
    <div ref="timeline" class="timeline" role="log" aria-label="提交前需求讨论" aria-live="polite">
      <div v-if="!messages.length" class="welcome"><span class="welcome-mark" aria-hidden="true">✦</span><h2>{{ mode === 'consultation' ? '想了解什么？' : mode === 'bug' ? '遇到了什么问题？' : '哪里可以更好？' }}</h2><div class="starter-options"><button v-for="sample in samples" :key="sample" type="button" @click="content = sample">{{ sample }}</button></div></div>
      <article v-for="(message, index) in messages" :key="index" :class="message.role">
        <strong>{{ message.role === 'user' ? '你' : '行影集 AI 助手' }}</strong>
        <ChatActivity v-if="message.activities?.length" :items="message.activities" />
        <div v-if="message.role === 'assistant'" class="response" v-html="renderConversationMarkdown(message.text)"></div><p v-else>{{ message.text }}</p>
        <details v-if="message.sources?.length" class="sources"><summary>参考资料 · {{ message.sources.length }}</summary><a v-for="source in message.sources" :key="source.url" :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.kind === 'code' ? '源码' : '文档' }} · {{ source.path }}<span v-if="source.kind === 'code'">:{{ source.line }}</span></a></details>
      </article>
      <article v-if="sending" class="assistant"><ChatActivity :items="activities" active /><ThinkingDots label="正在处理，请稍候" /></article>
    </div>
    <form class="panel composer" @submit.prevent="send">
      <ChatQuota :quota="quota" />
      <el-input v-model="content" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" :readonly="sending" resize="none" maxlength="2000" show-word-limit aria-label="讨论内容" placeholder="聊聊行影集，或补充刚才的细节…" @keydown="chatEnter($event, send)" />
      <div class="actions"><span>{{ cooldown > 0 ? `还需等待 ${cooldown} 秒` : 'Enter 发送 · Shift + Enter 换行' }}</span><el-button type="primary" native-type="submit" :loading="sending" :disabled="!content.trim() || sending || submitting || cooldown > 0 || quota?.exhausted">发送 ↑</el-button></div>
    </form>
    </div>
    <section v-if="draft" v-show="showPreview" class="panel preview" :class="{ expanded: showPreview }" aria-label="AI 整理的需求单">
      <div class="preview-title"><h2>需求单</h2><span class="draft-status" role="status">待确认</span><button class="preview-close" type="button" aria-label="关闭需求预览" @click="showPreview = false">×</button></div>
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
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, type Requirement } from '../../api'
import { intake, type Draft, type ChatMode, type Source, type Snapshot } from '../../api/intake'
import type { Quota } from '../../api/collaboration'
import { newEditToken, useAnonymousReceipts } from '../../stores/anonymousReceipts'
import { renderConversationMarkdown } from '../../conversationMarkdown'
import RequirementContact from '../../components/RequirementContact.vue'
import ChatQuota from '../../components/ChatQuota.vue'
import ThinkingDots from '../../components/ThinkingDots.vue'
import { chatEnter } from '../../chatKeyboard'
import ChatActivity from '../../components/ChatActivity.vue'
import type { ChatActivity as Activity } from '../../api/chatStream'

const router = useRouter(), receipts = useAnonymousReceipts()
const content = ref(''), email = ref(''), optIn = ref(false), sending = ref(false), submitting = ref(false), submitted = ref(false)
const draft = ref<Draft | null>(null), quota = ref<Quota>(), cooldown = ref(0)
const messages = ref<{ role: string; text: string; sources?: Source[]; activities?: Activity[] }[]>([])
const activities = ref<Activity[]>([])
let controller: AbortController | undefined, stopped = false
function updateActivity(event: Activity) {
  if (stopped || activities.value.length >= 24) return
  const last = activities.value[activities.value.length - 1]
  if (last?.kind === event.kind && last.status === 'running') Object.assign(last, event)
  else activities.value.push(event)
  void scrollToEnd()
}
const mode = ref<ChatMode>('feedback'), snapshot = ref<Snapshot>()
const modes: { value: ChatMode; label: string }[] = [{ value: 'feedback', label: '✦ 需求反馈' }, { value: 'bug', label: '⌕ 问题排查' }, { value: 'consultation', label: '？使用咨询' }]
const samples = computed(() => mode.value === 'consultation' ? ['行影集如何添加照片目录？', '行影集如何开启人脸识别？', '如何在飞牛 NAS 安装行影集？'] : mode.value === 'bug' ? ['行影集照片导出失败', '行影集登录后出现报错', '行影集地图轨迹有问题'] : ['行影集想增加批量操作', '想改进人物相册', '行影集照片导出体验优化'])
const timeline = ref<HTMLElement | null>(null), showPreview = ref(false)
let key = newEditToken(), state: string | undefined, creationKey = newEditToken()
let pendingSubmission: Record<string, unknown> | undefined
try {
  const saved = JSON.parse(sessionStorage.getItem('rp_intake') || 'null')
  if (saved?.key && saved?.state) { key = saved.key; state = saved.state; messages.value = saved.messages || []; draft.value = saved.draft; creationKey = saved.creationKey || creationKey; if (modes.some(m => m.value === saved.mode)) mode.value = saved.mode }
} catch { /* The current tab also keeps a copy in memory. */ }
const timer = setInterval(() => { if (cooldown.value > 0) cooldown.value-- }, 1000)
function persist() {
  try { sessionStorage.setItem('rp_intake', JSON.stringify({ key, state, messages: messages.value, draft: draft.value, creationKey, mode: mode.value })) } catch { /* Continue in memory. */ }
}
function reason(e: any) { return e?.response?.data?.msg || '暂时无法连接，请稍后重试，也可以填写表单提交' }
async function scrollToEnd() { await nextTick(); if (timeline.value) timeline.value.scrollTop = timeline.value.scrollHeight }
async function send() {
  if (sending.value || submitting.value || cooldown.value || quota.value?.exhausted || !content.value.trim()) return
  sending.value = true
  activities.value = []
  controller = new AbortController()
  const text = content.value.trim()
  messages.value.push({ role: 'user', text })
  await scrollToEnd()
  try {
    const result = await intake.stream(key, text, state, mode.value, updateActivity, controller.signal)
    if (stopped) return
    for (const activity of activities.value) if (activity.status === 'running') activity.status = 'completed'
    messages.value.push({ role: 'assistant', text: result.reply, sources: result.sources, activities: [...activities.value] })
    if (result.snapshot) snapshot.value = result.snapshot
    if (result.draft && !draft.value && window.innerWidth > 1000) showPreview.value = true
    draft.value = result.draft; quota.value = result.quota; state = result.state; content.value = ''
    cooldown.value = (result.quota as Quota & { retry_after_seconds?: number }).retry_after_seconds || 0
    pendingSubmission = undefined; persist()
  } catch (e: any) {
    if (stopped) return
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
onMounted(async () => { const results = await Promise.allSettled([intake.quota(key), intake.knowledge()]); if (results[0].status === 'fulfilled') { quota.value = results[0].value; cooldown.value = quota.value.retry_after_seconds || 0 } else { ElMessage.error(reason(results[0].reason)) } if (results[1].status === 'fulfilled') snapshot.value = results[1].value })
onBeforeUnmount(() => { stopped = true; controller?.abort(); clearInterval(timer) })
</script>

<style scoped>
.intake-page { height:100%; min-height:0; display:flex; flex-direction:column; width:100%; }
header { flex:none; display:flex; justify-content:space-between; align-items:center; gap:16px; padding:22px 32px 12px; }
h1 { margin:0; font-size:20px; letter-spacing:-.5px; } header p { margin:6px 0 0; font-size:13px; color:var(--rp-text-3); }
.header-actions { display:flex; gap:8px; }.header-actions .el-button { margin:0; }
.mode-tabs { display:flex; flex:none; gap:4px; margin:0 32px 10px; padding:4px; align-self:flex-start; border-radius:12px; background:var(--rp-bg); }
.mode-tabs button { border:0; background:transparent; color:var(--rp-text-2); border-radius:9px; min-height:36px; padding:8px 16px; cursor:pointer; transition:background .15s,color .15s; }
.mode-tabs button[aria-pressed=true] { color:var(--rp-primary); background:var(--rp-card); box-shadow:var(--rp-shadow); font-weight:600; }
.knowledge-status { display:flex; flex:none; align-items:center; gap:7px; font-size:11px; color:var(--rp-text-3); padding:0 32px 12px; overflow:hidden; }
.knowledge-status > span:nth-child(2) { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.knowledge-status small { font-size:11px; }
.status-dot { width:6px; height:6px; border-radius:50%; flex:none; background:var(--rp-text-3); }.status-dot.ready { background:var(--rp-primary); }
.intake-workspace { position:relative; flex:1; min-height:0; display:grid; grid-template-columns:minmax(0,1fr); }
.intake-workspace.preview-open { grid-template-columns:minmax(0,1fr) 380px; }
.chat-area { min-width:0; min-height:0; display:flex; flex-direction:column; }
.timeline { margin:0; border:0; flex:1; min-height:0; overflow-y:auto; overscroll-behavior:contain; padding:20px max(28px,calc((100% - 860px)/2)); scrollbar-width:thin; }
.timeline article { margin:0 0 28px; padding:0; overflow-wrap:anywhere; animation:arrive .2s ease-out; }
.timeline article strong { display:block; font-size:12px; font-weight:500; color:var(--rp-text-3); margin-bottom:10px; }
article.user { margin-left:auto; width:fit-content; max-width:85%; padding:14px 20px; background:var(--rp-primary-soft); border-radius:20px 20px 6px 20px; }
article.user strong { display:none; } article.user p { white-space:pre-wrap; margin:0; line-height:1.7; color:var(--rp-text); }
.response { line-height:1.85; font-size:15px; }.response :deep(p) { margin:8px 0; }.response :deep(h1),.response :deep(h2),.response :deep(h3) { font-size:1.1em; margin:20px 0 10px; }.response :deep(pre) { overflow:auto; padding:16px; border-radius:12px; background:var(--rp-bg); }.response :deep(table) { display:block; max-width:100%; overflow:auto; border-collapse:collapse; }.response :deep(th),.response :deep(td) { border:1px solid var(--rp-border); padding:6px 10px; }.response :deep(a),.sources a { color:var(--rp-primary); }.response :deep(ul),.response :deep(ol) { padding-left:24px; }
.sources { font-size:12px; color:var(--rp-text-3); margin-top:12px; }.sources summary { cursor:pointer; padding:8px 0; }.sources a { display:block; padding:6px 0; overflow-wrap:anywhere; }
.welcome { display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:100%; gap:20px; padding:24px 0; text-align:center; }.welcome h2 { margin:0; font-size:27px; letter-spacing:-.8px; }.welcome-mark { display:grid; place-items:center; width:64px; height:64px; border:1px solid var(--rp-border); border-radius:22px; color:var(--rp-primary); background:var(--rp-card); font-size:36px; box-shadow:var(--rp-shadow); }
.starter-options { display:flex; gap:8px; flex-wrap:wrap; justify-content:center; }.starter-options button { border:1px solid var(--rp-border); background:var(--rp-card); color:var(--rp-text-2); border-radius:14px; padding:12px 16px; cursor:pointer; min-height:44px; transition:transform .15s,border-color .15s; }.starter-options button:hover { transform:translateY(-2px); border-color:var(--rp-primary); color:var(--rp-primary); }
.composer { flex:none; width:calc(100% - 56px); max-width:860px; align-self:center; margin:8px 28px max(20px,env(safe-area-inset-bottom)); padding:10px 18px 12px; border-radius:22px; background:var(--rp-card); box-shadow:var(--rp-shadow); transition:border-color .15s; }.composer:focus-within { border-color:var(--rp-primary); }.composer :deep(.el-textarea__inner) { box-shadow:none; background:transparent; padding:8px 0 20px; font-size:16px; line-height:1.6; }.composer :deep(.el-input__count) { background:transparent; }.actions { display:flex; justify-content:space-between; gap:10px; align-items:center; margin-top:4px; }.actions span { color:var(--rp-text-3); font-size:11px; }.actions .el-button { flex:none; min-width:80px; min-height:40px; border-radius:13px; }
.preview { min-height:0; overflow-y:auto; overscroll-behavior:contain; margin:0; padding:22px; border-radius:0; border-width:0 0 0 1px; background:var(--rp-card); }.preview-title { display:flex; align-items:center; gap:12px; margin-bottom:22px; }.preview-title h2 { margin:0; font-size:18px; }.draft-status { font-size:12px; color:var(--rp-primary); }.preview-close { margin-left:auto; border:0; background:var(--rp-bg); color:var(--rp-text-2); width:36px; height:36px; font-size:24px; border-radius:10px; cursor:pointer; }.preview :deep(.el-select) { width:100%; }.preview :deep(.el-button[type=submit]) { width:100%; min-height:44px; }.privacy-note { font-size:12px; color:var(--rp-text-3); }
button:focus-visible { outline:2px solid var(--rp-primary); outline-offset:3px; }
@keyframes arrive { from { opacity:0; transform:translateY(5px) } to { opacity:1; transform:translateY(0) } }
@media(max-width:1000px) { .intake-workspace.preview-open { grid-template-columns:minmax(0,1fr); }.preview { position:absolute; inset:0 0 0 auto; width:min(100%,440px); z-index:5; box-shadow:var(--rp-shadow); } }
@media(max-width:600px) { header { padding:14px 16px 10px; gap:8px; }h1 { font-size:18px; } header p { display:none; }.header-actions .el-button { padding:8px 10px; }.mode-tabs { margin:0 12px 8px; align-self:stretch; }.mode-tabs button { flex:1; padding:8px 6px; font-size:13px; }.knowledge-status { padding:0 16px 8px; }.knowledge-status small { display:none; }.timeline { padding:16px; }.welcome { gap:16px; }.welcome h2 { font-size:23px; }.starter-options { flex-direction:column; width:100%; max-width:320px; }.starter-options button { text-align:left; }article.user { max-width:92%; padding:12px 16px; }.composer { width:calc(100% - 24px); margin:6px 12px max(10px,env(safe-area-inset-bottom)); padding:8px 12px 10px; border-radius:18px; }.actions span { font-size:10px; }.preview { padding:18px; } }
@media(max-height:600px) { .knowledge-status { display:none; }.composer :deep(.el-textarea__inner) { min-height:48px!important; height:48px!important; }.composer :deep(.chat-quota) { margin:0; }.timeline { padding-top:8px; padding-bottom:8px; } }
@media(prefers-reduced-motion:reduce) { .timeline article { animation:none; }.starter-options button { transition:none; } }
</style>
