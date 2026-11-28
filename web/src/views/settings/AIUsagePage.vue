<template>
  <section>
    <div class="page-head">
      <div class="page-head-left">
        <div class="page-head-icon"><el-icon :size="23"><TrendCharts /></el-icon></div>
        <div><h1>AI 使用看板</h1><p class="sub">查看模型用量、每段对话的 Token 统计及已保存的对话记录。</p></div>
      </div>
    </div>
    <AIUsageOverview />
    <article class="panel conversations" aria-labelledby="ai-conversations-title">
      <div class="section-head">
        <h2 id="ai-conversations-title">按对话查看</h2>
        <el-button :loading="loading" @click="loadList">刷新对话</el-button>
      </div>
      <el-radio-group v-model="kind" aria-label="对话类型">
        <el-radio-button value="requirement">需求对话</el-radio-button>
        <el-radio-button value="intake">AI 助手</el-radio-button>
      </el-radio-group>
      <p class="note">按对话汇总已关联的用量。升级前的调用未关联到对话；“无记录”不代表没有消耗。</p>
      <p v-if="kind === 'intake'" class="note">新版 AI 助手保存文字问答。旧会话若只有用量，则无法查看正文；照片与文件原件不会保存。</p>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-table v-loading="loading" :data="rows" :empty-text="error ? '未能载入对话' : '暂无对话记录'">
        <el-table-column label="对话" min-width="220">
          <template #default="{ row }">
            <el-button v-if="row.has_transcript" link type="primary" class="conversation-link" @click="selected = row">
              {{ conversationLabel(row, kind) }}
            </el-button>
            <span v-else>{{ conversationLabel(row, kind) }} <small>旧记录 · 无正文</small></span>
            <small>{{ date(row.updated_at) }}</small>
          </template>
        </el-table-column>
        <el-table-column label="模型调用" min-width="120"><template #default="{row}">{{ tokens(row.requests) }} 次<small v-if="row.failed">{{ row.failed }} 次失败</small></template></el-table-column>
        <el-table-column label="输入 / 输出 Token" min-width="170">
          <template #default="{row}">
            {{ reported(row) }}
            <small v-if="row.unreported">{{ row.unreported }} 次未完整上报</small>
          </template>
        </el-table-column>
        <el-table-column label="预留 Token" min-width="120"><template #default="{row}">{{ row.requests ? tokens(row.reserved_tokens) : '—' }}</template></el-table-column>
      </el-table>
      <el-pagination v-if="total > 20" v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next" :pager-count="5" />
    </article>

    <el-dialog :model-value="!!selected" :title="selected ? `${conversationLabel(selected, kind)} · 对话详情` : '对话详情'"
      width="min(760px, calc(100vw - 24px))" destroy-on-close @update:model-value="$event || (selected = null)">
      <div v-loading="detailLoading" class="detail">
        <p class="note">仅管理员可见。查看会记录在审计日志中；消息按最新优先显示。</p>
        <div v-if="detailError" class="section-head">
          <span role="alert">{{ detailError }}</span><el-button @click="loadMessages">重试</el-button>
        </div>
        <el-empty v-else-if="!detailLoading && !messages.length" description="暂无消息" />
        <article v-for="message in messages" :key="message.id" class="message">
          <header>{{ date(message.created_at) }} · {{ (kind === 'intake' ? intakeModes : modes)[message.mode] || message.mode }} · {{ statuses[message.status] || message.status }}</header>
          <p class="note">输入 / 输出：{{ reported(message) }}<template v-if="message.requests"> · {{ message.requests }} 次调用 · 预留 {{ tokens(message.reserved_tokens) }} Token</template><template v-if="message.failed"> · {{ message.failed }} 次失败</template><template v-if="message.unreported"> · {{ message.unreported }} 次未完整上报</template></p>
          <strong>提问</strong><p class="message-text">{{ message.content || '未填写文字' }}</p>
          <p v-if="message.image_count || message.file_count" class="note">附件：{{ message.image_count }} 张照片、{{ message.file_count }} 个文件（不保留原件）</p>
          <strong>回复</strong><p class="message-text">{{ message.response ?? '暂无回复' }}</p>
          <details v-if="message.tool_calls?.length" class="tool-calls">
            <summary>工具调用（{{ message.tool_calls.length }} 次已记录）</summary>
            <ol>
              <li v-for="(tool, index) in message.tool_calls" :key="index">
                <code>{{ tool.name }}</code> · {{ toolStatuses[tool.status] }} · <time :datetime="tool.created_at">{{ date(tool.created_at) }}</time>
              </li>
            </ol>
            <p class="note">仅记录工具名称、时间和状态，不保存参数或返回内容。</p>
          </details>
          <p v-else class="note">{{ message.tool_calls === null ? '没有可查看的工具记录（旧记录或模型未被调用）' : '未观察到工具调用' }}</p>
        </article>
        <el-pagination v-if="messageTotal > 20" v-model:current-page="messagePage" :page-size="20" :total="messageTotal" layout="prev, pager, next" :pager-count="5" />
      </div>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { TrendCharts } from '@element-plus/icons-vue'
import AIUsageOverview from '../../components/usage/AIUsageOverview.vue'
import { aiUsage, type AIConversation, type AIMessage, type ConversationKind, type UsageCounts } from '../../api/aiUsage'

const kind = ref<ConversationKind>('requirement')
const rows = ref<AIConversation[]>([]), page = ref(1), total = ref(0), loading = ref(false), error = ref('')
const selected = ref<AIConversation | null>(null)
const messages = ref<AIMessage[]>([]), messagePage = ref(1), messageTotal = ref(0), detailLoading = ref(false), detailError = ref('')
const modes: Record<string, string> = { analysis: '需求分析', plan: '方案', repair: '修复建议', consultation: '协作提问' }
const intakeModes: Record<string, string> = { feedback: '需求反馈', bug: '问题排查', consultation: '使用咨询' }
const conversationLabel = (row: AIConversation, type: ConversationKind) => type === 'requirement'
  ? `REQ-${row.requirement_number} · ${row.title}` : `AI 助手 · ${row.id.slice(0, 8)}`
const statuses: Record<string, string> = { queued: '排队中', running: '处理中', completed: '已回复', failed: '失败' }
const toolStatuses = { completed: '成功', failed: '失败', unconfirmed: '结果未确认' }
const tokens = (value: number) => value.toLocaleString('zh-CN')
const date = (value: string) => new Date(value).toLocaleString('zh-CN')
const reported = (row: UsageCounts) => !row.requests ? '无记录'
  : row.unreported === row.requests && !row.input_tokens && !row.output_tokens ? '未上报'
  : `${tokens(row.input_tokens)} / ${tokens(row.output_tokens)}`
let listRequest = 0, detailRequest = 0

async function loadList() {
  const request = ++listRequest
  loading.value = true; error.value = ''; rows.value = []
  try {
    const result = await aiUsage.conversations(kind.value, page.value)
    if (request !== listRequest) return
    rows.value = result.items; total.value = result.total
  } catch {
    if (request === listRequest) error.value = '无法读取对话列表，请刷新重试。'
  } finally {
    if (request === listRequest) loading.value = false
  }
}
async function loadMessages() {
  const request = ++detailRequest
  messages.value = []; detailError.value = ''; detailLoading.value = !!selected.value
  if (!selected.value) return
  try {
    const result = await aiUsage.messages(selected.value.id, messagePage.value, kind.value)
    if (request !== detailRequest) return
    messages.value = result.items; messageTotal.value = result.total
  } catch {
    if (request === detailRequest) detailError.value = '无法读取对话详情。'
  } finally {
    if (request === detailRequest) detailLoading.value = false
  }
}
watch(kind, () => { total.value = 0; page.value = 1; selected.value = null }, { flush: 'sync' })
watch([kind, page], loadList, { immediate: true })
watch(selected, () => { messageTotal.value = 0; messagePage.value = 1 }, { flush: 'sync' })
watch([selected, messagePage], loadMessages)
</script>

<style scoped>
.conversations { padding: clamp(12px, 2vw, 22px); }
.section-head { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }
h2 { font-size: 19px; margin: 0; }
.note, small, .message header { color: var(--rp-text-3); font-size: 12px; }
.note { line-height: 1.6; }
small { display: block; }
.conversation-link { white-space: normal; text-align: left; height: auto; }
.detail { min-height: 90px; }
.message { padding: 14px 0; border-top: 1px solid var(--rp-border); }
.message-text { white-space: pre-wrap; overflow-wrap: anywhere; margin: 4px 0 12px; }
.tool-calls { background: var(--rp-surface-muted); padding: 10px 12px; border: 1px solid var(--rp-border); border-radius: 8px; overflow-wrap: anywhere; }
.tool-calls summary { cursor: pointer; font-weight: 600; }
.tool-calls ol { margin: 8px 0; padding-inline-start: 24px; line-height: 1.8; }
.el-pagination { margin-top: 14px; }
</style>
