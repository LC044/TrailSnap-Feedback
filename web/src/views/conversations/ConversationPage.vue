<template>
  <section class="conversation-page">
    <header class="conversation-head">
      <div><h1>REQ-{{ number }} · 需求讨论</h1></div>
      <el-button @click="router.push(`/requirements/REQ-${number}`)">查看需求</el-button>
    </header>
    <el-alert v-if="error" type="error" :closable="false" :title="error"><el-button link @click="reload">重新加载</el-button></el-alert>
    <div v-if="loading" class="empty" role="status">正在恢复对话…</div>
    <div v-else ref="timeline" class="conversation-timeline" role="log" aria-live="polite" aria-label="需求对话">
      <div v-if="!messages.length && ready" class="conversation-welcome">
        <div class="assistant-avatar">行</div><h2>聊聊你的想法</h2>
        <p>补充细节，或继续完善需求。</p>
        <div class="suggestions"><el-button v-for="suggestion in suggestions" :key="suggestion" @click="draft = suggestion">{{ suggestion }}</el-button></div>
      </div>
      <article v-for="message in messages" :key="message.id" class="conversation-turn">
        <div class="user-message"><span>{{ message.mode === 'consultation' ? '维护者' : '你' }}</span><p>{{ message.content }}</p></div>
        <div class="assistant-message"><div class="assistant-avatar">{{ message.mode === 'consultation' ? '问' : '行' }}</div><div class="assistant-content">
          <div v-if="message.response" class="message-text" v-html="renderConversationMarkdown(message.response)"></div>
          <p v-else-if="message.status === 'failed'" role="alert">{{ message.error }} <el-button link type="primary" @click="retry(message.id)">重试</el-button></p>
          <ThinkingDots v-else :label="message.status === 'running' ? '正在分析' : '等待分析'" />
        </div></div>
      </article>
    </div>
    <form v-if="ready" class="conversation-composer" @submit.prevent="send">
      <div class="composer-options"><span>行影集 AI 助手</span>
        <el-select v-if="canPlan" v-model="mode" aria-label="对话任务" style="width:160px"><el-option label="需求分析" value="analysis" /><el-option label="实现方案" value="plan" /><el-option label="修复建议 / 补丁" value="repair" /></el-select>
      </div>
      <ChatQuota :quota="quota" />
      <el-input v-model="draft" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" :maxlength="2000" show-word-limit resize="none" placeholder="补充细节，或回答 AI 的提问…" aria-label="对话内容" @keydown.ctrl.enter.prevent="send" @keydown.meta.enter.prevent="send" />
      <div class="composer-actions"><small>{{ cooldown ? `${cooldown} 秒后可发送` : '仅讨论行影集' }}</small><el-button native-type="submit" type="primary" :loading="sending" :disabled="pending || !draft.trim() || quota?.exhausted || cooldown > 0">发送</el-button></div>
    </form>
    <details v-if="ready" class="conversation-subscribe"><summary>通过邮箱跟进此需求</summary><form @submit.prevent="subscribe"><el-input v-model="email" type="email" placeholder="你的邮箱" aria-label="通知邮箱" required /><el-button native-type="submit" :loading="subscribing">订阅通知</el-button></form><p>请到邮箱确认订阅，可随时退订。邮件不公开显示你的邮箱。</p></details>
    <details v-if="canPlan" class="conversation-subscribe"><summary>向提交者发起咨询</summary><el-input v-model="question" type="textarea" :rows="3" maxlength="4000" placeholder="请用户补充的信息（将保存在其对话中，并通过邮件提醒）" /><el-button :disabled="question.trim().length < 4" :loading="consulting" @click="consult">发送咨询</el-button></details>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { collaboration, type Message, type Quota } from '../../api/collaboration'
import { useAnonymousReceipts, newEditToken } from '../../stores/anonymousReceipts'
import { renderConversationMarkdown } from '../../conversationMarkdown'
import ChatQuota from '../../components/ChatQuota.vue'
import ThinkingDots from '../../components/ThinkingDots.vue'

const props = defineProps<{ number: number }>()
const router = useRouter()
const route = useRoute()
const receipts = useAnonymousReceipts()
const id = `REQ-${props.number}`
// Receipts are indexed by UUID; use the matching public number when opening a route.
let emailToken = new URLSearchParams(route.hash.slice(1)).get('conversation_token') || ''
try {
  if (emailToken) { sessionStorage.setItem(`rp_conversation_${props.number}`, emailToken); history.replaceState(history.state, '', location.pathname + location.search) }
  else emailToken = sessionStorage.getItem(`rp_conversation_${props.number}`) || ''
} catch { /* Keep the scoped token in memory when storage is unavailable. */ }
const token = computed(() => receipts.receipts.find(r => r.number === props.number)?.token || emailToken || undefined)
const messages = ref<Message[]>([])
const quota = ref<Quota>()
const cooldown = ref(0)
const cooldownTimer = setInterval(() => { if (cooldown.value > 0) cooldown.value-- }, 1000)
const draft = ref(''), mode = ref('analysis'), email = ref(''), question = ref('')
const error = ref(''), canPlan = ref(false), ready = ref(false), loading = ref(true), sending = ref(false), subscribing = ref(false), consulting = ref(false)
const timeline = ref<HTMLElement | null>(null)
const pending = computed(() => messages.value.some(m => ['queued', 'running'].includes(m.status)))
const suggestions = ['你还需要我补充哪些信息？', '帮我梳理这个需求的使用场景', '我们一起确认预期结果']
let timer: ReturnType<typeof setTimeout> | undefined
let stopped = false
let pendingSend: { content: string; mode: string; id: string } | undefined
function reason(e: any) { return e?.response?.data?.msg || e?.response?.data?.detail || '暂时无法连接，请稍后重试' }
async function reload() {
  clearTimeout(timer)
  try {
    const data = await collaboration.read(id, token.value)
    if (stopped) return
    messages.value = data.messages; canPlan.value = data.can_plan; quota.value = data.quota; cooldown.value = data.quota.retry_after_seconds || 0; error.value = ''; ready.value = true
    await nextTick()
    if (timeline.value) timeline.value.scrollTop = timeline.value.scrollHeight
  } catch (e) { if (!stopped) error.value = reason(e) }
  finally {
    loading.value = false
    if (!stopped && (pending.value || error.value)) timer = setTimeout(reload, error.value ? 10000 : 1500)
  }
}
async function send() {
  if (sending.value || pending.value || cooldown.value || quota.value?.exhausted || !draft.value.trim()) return
  sending.value = true
  if (!pendingSend || pendingSend.content !== draft.value.trim() || pendingSend.mode !== mode.value) pendingSend = { content: draft.value.trim(), mode: mode.value, id: newEditToken() }
  try { await collaboration.send(id, pendingSend.content, pendingSend.id, pendingSend.mode, token.value); draft.value = ''; pendingSend = undefined; await reload() }
  catch (e) { ElMessage.error(reason(e)) }
  finally { sending.value = false }
}
async function retry(message: string) { try { await collaboration.retry(id, message, token.value); await reload() } catch (e) { ElMessage.error(reason(e)) } }
async function subscribe() { subscribing.value = true; try { await collaboration.subscribe(id, email.value, token.value); ElMessage.success('请到邮箱确认订阅') } catch(e) { ElMessage.error(reason(e)) } finally { subscribing.value = false } }
async function consult() { consulting.value = true; try { await collaboration.consult(id, question.value); question.value = ''; ElMessage.success('咨询已保存，并加入通知队列') } catch(e) { ElMessage.error(reason(e)) } finally { consulting.value = false } }
onMounted(reload)
onBeforeUnmount(() => { stopped = true; clearTimeout(timer); clearInterval(cooldownTimer) })
</script>

<style scoped>
.conversation-page { max-width: 960px; margin:auto; display:flex; flex-direction:column; min-height:72vh; }
.conversation-head { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:12px 0 24px; }
.conversation-head h1 { font-size:22px; margin:6px 0; overflow-wrap:anywhere; }
.eyebrow { color:var(--rp-text-2); font-size:13px; margin:0; }
.conversation-timeline { flex:1; max-height:58vh; min-height:260px; overflow-y:auto; padding:16px 8px; scrollbar-width:thin; }
.conversation-welcome { text-align:center; padding:28px 0; color:var(--rp-text-2); }
.conversation-welcome .assistant-avatar { margin:auto; }.conversation-welcome h2 { color:var(--rp-text); }
.suggestions { display:flex; flex-wrap:wrap; justify-content:center; gap:8px; }.suggestions .el-button { margin:0; white-space:normal; height:auto; min-height:44px; }
.conversation-turn { margin-bottom:28px; }.user-message { max-width:85%; margin-left:auto; text-align:right; }.user-message span { color:var(--rp-text-3); font-size:12px; }.user-message p { display:block; text-align:left; white-space:pre-wrap; overflow-wrap:anywhere; background:var(--rp-primary-soft); border-radius:18px 18px 4px 18px; padding:16px; margin:6px 0 20px; }
.assistant-message { display:flex; gap:12px; }.assistant-avatar { width:36px; height:36px; flex-shrink:0; border-radius:12px; display:grid; place-items:center; background:var(--rp-primary); color:var(--rp-card); font-weight:700; }.assistant-content { min-width:0; flex:1; }.message-text { white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.85; margin:0; }.pending { color:var(--rp-text-2); }
.conversation-composer { position:sticky; bottom:12px; background:var(--rp-card); border:1px solid var(--rp-border); border-radius:20px; padding:14px; box-shadow:var(--rp-shadow); }.composer-options,.composer-actions { display:flex; justify-content:space-between; align-items:center; gap:12px; }.composer-options { margin-bottom:10px; color:var(--rp-text-2); font-size:13px; }.composer-actions { margin-top:10px; }.composer-actions small { color:var(--rp-text-3); }.composer-actions .el-button { min-height:44px; }
.conversation-subscribe { color:var(--rp-text-2); padding:18px 6px; font-size:13px; }.conversation-subscribe summary { cursor:pointer; min-height:30px; }.conversation-subscribe form { display:flex; gap:8px; margin-top:12px; }
.message-text { white-space:normal; }
.message-text :deep(:first-child) { margin-top:0; }
.message-text :deep(:last-child) { margin-bottom:0; }
.message-text :deep(h1),.message-text :deep(h2),.message-text :deep(h3) { font-size:1.1em; line-height:1.5; margin:20px 0 10px; }
.message-text :deep(ul),.message-text :deep(ol) { padding-left:24px; }
.message-text :deep(a) { color:var(--rp-primary); }
.message-text :deep(pre),.message-text :deep(table) { max-width:100%; overflow-x:auto; }
.message-text :deep(pre) { background:var(--rp-primary-soft); padding:12px; border-radius:10px; }
.message-text :deep(code) { font-size:.9em; overflow-wrap:anywhere; }
.message-text :deep(table) { display:block; border-collapse:collapse; }
.message-text :deep(th),.message-text :deep(td) { border:1px solid var(--rp-border); padding:6px 10px; }
@media(max-width:600px) { .conversation-head h1{font-size:18px}.conversation-head { align-items:flex-start; }.conversation-timeline{max-height:52dvh}.composer-actions small{max-width:62%;line-height:1.5}.user-message{max-width:94%}.conversation-subscribe form{flex-wrap:wrap} }
.conversation-composer :deep(.el-textarea__inner){box-shadow:none;padding:8px 0;font-size:15px}.conversation-timeline{scrollbar-width:thin}.conversation-head{padding:8px 0 16px}.composer-options{margin-bottom:0}
@media(max-width:600px){.conversation-timeline{min-height:220px;max-height:45dvh}.conversation-composer{bottom:8px;padding:12px;border-radius:16px}}
</style>
