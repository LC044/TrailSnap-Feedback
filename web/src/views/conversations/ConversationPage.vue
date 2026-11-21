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
      <el-input v-model="draft" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" :maxlength="2000" show-word-limit :readonly="sending || pending" resize="none" placeholder="补充细节，或回答 AI 的提问…" aria-label="对话内容" @keydown="chatEnter($event, send)" />
      <div class="composer-actions"><small>{{ cooldown ? `${cooldown} 秒后可发送` : 'Enter 发送 · Shift + Enter 换行' }}</small><el-button native-type="submit" type="primary" :loading="sending" :disabled="pending || !draft.trim() || quota?.exhausted || cooldown > 0">发送 ↑</el-button></div>
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
import { chatEnter } from '../../chatKeyboard'

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
.conversation-page {
  width: 100%; height: 100%; min-height: 0; max-width: none;
  padding: 0 28px; overflow: hidden;
  display: flex; flex-direction: column;
}
.conversation-head {
  flex: none;
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  padding: 18px 4px 12px;
  border-bottom: 1px solid color-mix(in srgb, var(--line) 70%, transparent);
}
.conversation-head h1 {
  display: flex; align-items: center; gap: 10px;
  font-size: 16px; font-weight: 700; letter-spacing: -.015em; margin: 0;
  overflow-wrap: anywhere;
}
.conversation-head h1::before {
  content: "REQ";
  display: inline-grid; place-items: center;
  height: 20px; padding: 0 7px; border-radius: 6px;
  background: var(--primary-soft); color: var(--primary);
  font-size: 9.5px; font-weight: 800; letter-spacing: .04em;
}
.conversation-head h1 { font-variant-numeric: tabular-nums; }

.conversation-timeline {
  flex: 1; min-height: 0; max-height: none;
  overflow-y: auto; overscroll-behavior: contain;
  padding: 20px max(4px, calc((100% - 800px) / 2));
  scrollbar-width: thin;
}
.conversation-welcome { text-align: center; padding: 34px 0; color: var(--ink-3); }
.conversation-welcome .assistant-avatar { margin: 0 auto 12px; }
.conversation-welcome h2 { color: var(--ink); font-size: 22px; letter-spacing: -.025em; }
.conversation-welcome p { color: var(--ink-3); font-size: 12.5px; margin: 6px 0 16px; }
.suggestions { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; }
.suggestions .el-button { margin: 0; white-space: normal; height: auto; min-height: 40px; border-radius: 11px; }

.conversation-turn { margin-bottom: 26px; animation: arrive .3s var(--ease-out); }
@keyframes arrive { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
.user-message { max-width: 84%; margin-left: auto; text-align: right; }
.user-message span { color: var(--ink-4); font-size: 11px; }
.user-message p {
  display: block; text-align: left; white-space: pre-wrap; overflow-wrap: anywhere;
  padding: 12px 16px; margin: 6px 0 18px;
  border-radius: 18px 18px 5px 18px;
  color: #fff;
  background: linear-gradient(135deg, var(--primary), var(--primary-bright));
  box-shadow: 0 12px 26px -18px color-mix(in srgb, var(--primary) 95%, transparent);
  font-size: 13.5px; line-height: 1.7;
}
.assistant-message { display: flex; gap: 12px; }
.assistant-avatar {
  width: 32px; height: 32px; flex-shrink: 0;
  border-radius: 11px; display: grid; place-items: center;
  color: #fff; font-weight: 700; font-size: 13px;
  background: linear-gradient(135deg, var(--primary), var(--brand-teal));
  box-shadow: 0 8px 18px -10px color-mix(in srgb, var(--primary) 90%, transparent);
}
.assistant-content { min-width: 0; flex: 1; }
.message-text { white-space: normal; overflow-wrap: anywhere; line-height: 1.85; margin: 0; font-size: 14px; color: var(--ink); }
.pending { color: var(--ink-2); }

.conversation-composer {
  position: static; flex: none;
  width: 100%; max-width: 800px; align-self: center;
  margin: 8px 0 0; padding: 12px 16px;
  border: 1px solid var(--line); border-radius: 20px;
  background: var(--surface);
  box-shadow: 0 18px 40px -30px rgba(16, 22, 45, .5);
  transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}
.conversation-composer:focus-within {
  border-color: color-mix(in srgb, var(--primary) 42%, var(--line));
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--primary) 9%, transparent), 0 18px 40px -30px rgba(16, 22, 45, .5);
}
.composer-options, .composer-actions { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.composer-options { margin-bottom: 2px; color: var(--ink-3); font-size: 12px; }
.composer-actions { margin-top: 8px; }
.composer-actions small { color: var(--ink-4); font-size: 11px; }
.composer-actions .el-button { min-height: 38px; min-width: 84px; border-radius: 11px; }
.conversation-composer :deep(.el-textarea__inner) { box-shadow: none; background: transparent; padding: 8px 0 18px; font-size: 15px; line-height: 1.65; }

.conversation-subscribe {
  flex: none; width: 100%; max-width: 800px; align-self: center;
  padding: 8px 4px; max-height: 28%; overflow-y: auto;
  color: var(--ink-2); font-size: 12.5px;
}
.conversation-subscribe summary { cursor: pointer; min-height: 24px; padding: 3px 0; }
.conversation-subscribe:last-child { margin-bottom: max(8px, env(safe-area-inset-bottom)); }
.conversation-subscribe form { display: flex; gap: 8px; margin-top: 10px; }
.conversation-subscribe p { color: var(--ink-4); font-size: 11.5px; margin-top: 6px; }

.message-text :deep(:first-child) { margin-top: 0; }
.message-text :deep(:last-child) { margin-bottom: 0; }
.message-text :deep(h1), .message-text :deep(h2), .message-text :deep(h3) { font-size: 1.08em; line-height: 1.5; margin: 20px 0 10px; }
.message-text :deep(ul), .message-text :deep(ol) { padding-left: 22px; }
.message-text :deep(a) { color: var(--primary); }
.message-text :deep(pre), .message-text :deep(table) { max-width: 100%; overflow-x: auto; }
.message-text :deep(pre) { background: var(--surface-2); border: 1px solid var(--line); padding: 12px; border-radius: 10px; }
.message-text :deep(code) { font-size: .92em; overflow-wrap: anywhere; }
.message-text :deep(table) { display: block; border-collapse: collapse; }
.message-text :deep(th), .message-text :deep(td) { border: 1px solid var(--line); padding: 6px 10px; }

@media (max-width: 600px) {
  .conversation-page { padding: 0 12px; }
  .conversation-head { padding: 12px 0 10px; }
  .conversation-head h1 { font-size: 14px; }
  .conversation-timeline { padding: 16px 0; }
  .conversation-composer { border-radius: 17px; padding: 10px 12px; }
  .assistant-avatar { width: 28px; height: 28px; border-radius: 9px; }
  .assistant-message { gap: 9px; }
  .user-message { max-width: 94%; }
  .composer-actions small { max-width: 60%; line-height: 1.5; font-size: 10px; }
  .conversation-subscribe form { flex-wrap: wrap; }
}
</style>
