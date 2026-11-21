<template>
  <div class="detail-page">
    <button class="detail-back" type="button" @click="emit('back')">
      <el-icon><ArrowLeft /></el-icon>返回需求列表
    </button>

    <header class="detail-hero">
      <div class="dh-main">
        <div class="dh-eyebrow">
          <span class="req-number">REQ-{{ requirement.public_number }}</span>
          <span class="tag no-dot" :class="`t-${requirement.type}`">{{ typeLabel(requirement.type) }}</span>
          <span class="tag" :class="`s-${requirement.status}`">{{ statusLabel(requirement.status) }}</span>
        </div>
        <h1>{{ requirement.title }}</h1>
        <div class="detail-meta">
          <span class="avatar" :style="{ ...avatarColor(requirement.created_by_name || '用户'), width: '24px', height: '24px', fontSize: '10px' }">{{ (requirement.created_by_name || '用户').slice(0, 1) }}</span>
          <strong>{{ requirement.created_by_name || '用户' }}</strong>
          <span class="dot">·</span>
          <span>{{ formatDateTime(requirement.created_at) }}</span>
          <span class="dot">·</span>
          <span class="meta-follow"><el-icon :size="12"><Star /></el-icon>{{ requirement.follower_count || 0 }} 人关注</span>
        </div>
      </div>
      <div class="dh-actions">
        <el-button class="dh-link" :icon="Link" @click="emit('copyLink')">复制链接</el-button>
        <el-button v-if="canFollow" :icon="Star" @click="emit('follow')">关注</el-button>
        <el-button v-if="manager || canEdit" type="primary" :icon="Edit" @click="emit('edit')">编辑需求</el-button>
      </div>
    </header>

    <!-- ============ 生命周期 ============ -->
    <section class="trail-card" aria-label="需求进展">
      <ol class="trail-steps">
        <li v-for="(stage, index) in trailStages" :key="stage.key"
          :class="{ done: trail.index > index, now: trail.index === index, stopped: trail.stopped && index === 0 }">
          <span class="ts-dot"><el-icon v-if="trail.index > index" :size="10"><Check /></el-icon></span>
          <span class="ts-label">{{ stage.short }}</span>
        </li>
      </ol>
      <div class="trail-note">
        <el-icon :size="15"><Promotion /></el-icon>
        <p><strong>接下来</strong>{{ nextAction(requirement.status) }}</p>
      </div>
    </section>

    <div class="detail-layout">
      <div class="detail-main">
        <article class="panel detail-content">
          <section class="content-block">
            <h2 class="detail-section-title"><span class="detail-section-icon">概</span>需求描述</h2>
            <div class="markdown-body" v-html="renderMarkdown(requirement.description)"></div>
          </section>

          <section v-if="requirement.steps_to_reproduce" class="content-block">
            <h2 class="detail-section-title"><span class="detail-section-icon">复</span>复现步骤</h2>
            <div class="markdown-body" v-html="renderMarkdown(requirement.steps_to_reproduce)"></div>
          </section>
          <section v-if="requirement.current_behavior" class="content-block">
            <h2 class="detail-section-title"><span class="detail-section-icon">现</span>当前行为</h2>
            <div class="markdown-body" v-html="renderMarkdown(requirement.current_behavior)"></div>
          </section>
          <section v-if="requirement.expected_behavior" class="content-block">
            <h2 class="detail-section-title"><span class="detail-section-icon">期</span>期望行为</h2>
            <div class="markdown-body" v-html="renderMarkdown(requirement.expected_behavior)"></div>
          </section>

          <div v-if="requirement.triage" class="triage-box">
            <div class="triage-head">
              <span class="triage-orb"><el-icon :size="13"><MagicStick /></el-icon></span>
              AI 分析已完成
              <span v-if="requirement.triage_model" class="triage-model">{{ requirement.triage_model }}</span>
            </div>
            <div class="markdown-body compact" v-html="renderMarkdown(triageText)"></div>
            <div v-if="confirmedFacts.length" class="analysis-list"><strong>已确认的信息</strong><ul><li v-for="(fact, index) in confirmedFacts" :key="index">{{ fact }}</li></ul></div>
            <div v-if="acceptanceDraft.length" class="analysis-list"><strong>验收草案</strong><ul><li v-for="(item, index) in acceptanceDraft" :key="index">{{ item }}</li></ul></div>
            <div class="analysis-next"><strong>下一步</strong><span>{{ nextStep }}</span></div>
            <div v-if="canEditSummary" class="summary-correction">
              <el-input v-model="summaryCorrection" type="textarea" :rows="2" placeholder="如果理解有偏差，可在这里纠正摘要" />
              <el-button :loading="saving" @click="saveSummary">提交纠正</el-button>
            </div>
          </div>
          <div v-else class="triage-box triage-pending">
            <div class="triage-head"><span class="triage-orb spinning"><el-icon :size="13"><MagicStick /></el-icon></span>AI 正在分析</div>
            <p>需求已进入后台分诊队列，正在生成问题摘要、完整度判断、重复候选与验收草案。完成后结果会显示在这里。</p>
          </div>

          <div v-if="openClarifications.length" class="clarification-box">
            <strong>还需要的信息</strong>
            <article v-for="question in openClarifications" :key="question.id">
              <p>{{ question.question }}<small>{{ question.rationale }}</small></p>
              <el-select v-if="question.suggested_options.length" v-model="answers[question.question_id]" allow-create filterable placeholder="选择或输入答案">
                <el-option v-for="option in question.suggested_options" :key="option" :label="option" :value="option" />
              </el-select>
              <el-input v-else v-model="answers[question.question_id]" type="textarea" :rows="2" placeholder="也可以回答“不确定”" />
              <el-button type="primary" size="small" :loading="saving" @click="answer(question.question_id)">提交答复</el-button>
            </article>
          </div>

          <div v-if="requirement.review_reason" class="review-note">
            <strong>审核说明</strong>
            <div class="markdown-body compact" v-html="renderMarkdown(requirement.review_reason)"></div>
          </div>
          <div v-if="requirement.log_text" class="log-panel">
            <strong>日志（仅本人和管理员可见）</strong>
            <pre class="log-text">{{ requirement.log_text }}</pre>
          </div>
          <div v-if="requirement.attachments?.length" class="attachments">
            <strong>附件（仅本人和管理员可见）</strong>
            <div v-for="attachment in requirement.attachments" :key="attachment.id" class="file-row">
              <span>{{ attachment.name }}（{{ formatBytes(attachment.size_bytes) }} · {{ attachment.processing_status === 'stored' ? '已安全保存' : attachment.processing_status }}）</span>
              <el-button link type="primary" @click="emit('download', attachment)">下载</el-button>
            </div>
          </div>
          <div v-if="manager && requirement.submitter_contact" class="contact-box">
            <strong>提交人联系方式（仅管理员可见）：</strong>{{ requirement.submitter_contact }}
          </div>
        </article>

        <DeliveryWorkspace v-if="manager" :requirement="requirement" :user-role="userRole" @refresh="emit('refresh')" />

        <article class="panel supplements-panel">
          <div class="supplement-head">
            <h2 class="detail-section-title" style="margin:0"><span class="detail-section-icon">补</span>补充说明</h2>
            <span class="chip">{{ supplements.length }}</span>
          </div>
          <p class="field-hint">补充复现条件、使用场景或方案调整，保留原需求正文。补充内容由维护者评估，不代表已经采纳。</p>
          <p v-if="supplementsError" role="alert">补充说明加载失败。<el-button link type="primary" @click="emit('refresh')">重试</el-button></p>
          <p v-else-if="!supplements.length" class="supplement-empty">暂时没有补充说明。</p>
          <section v-for="note in supplements" :key="note.id" class="supplement-item">
            <div class="supplement-meta">
              <span class="avatar" :style="{ ...avatarColor(note.author_name), width: '22px', height: '22px', fontSize: '10px' }">{{ note.author_name.slice(0, 1) }}</span>
              <strong>{{ note.author_name }}</strong>
              <span class="field-hint" style="margin:0">{{ formatDateTime(note.created_at) }}</span>
            </div>
            <p class="supplement-body">{{ note.body }}</p>
          </section>
          <el-button v-if="canSupplement" :icon="EditPen" @click="emit('supplement')">补充信息</el-button>
          <p v-else class="field-hint">这是你提交的需求？请用原浏览器或保存的私有管理链接打开，恢复修改权限。</p>
        </article>
      </div>

      <aside class="detail-sidebar">
        <article class="panel side-status">
          <dl class="status-fields">
            <div>
              <dt><el-icon><View /></el-icon>需求状态</dt>
              <dd>
                <button class="status-control" type="button" :disabled="!manager" @click="emit('status')">
                  <span class="tag" :class="`s-${requirement.status}`">{{ statusLabel(requirement.status) }}</span>
                  <el-icon v-if="manager" :size="12"><ArrowDown /></el-icon>
                </button>
              </dd>
            </div>
            <div><dt><el-icon><Warning /></el-icon>优先级</dt><dd><span class="tag no-dot" :class="`p-${requirement.priority}`">{{ priorityLabel(requirement.priority) }}</span></dd></div>
            <div><dt><el-icon><User /></el-icon>负责人</dt><dd>{{ requirement.assignee_name || '未指派' }}</dd></div>
            <div><dt><el-icon><Flag /></el-icon>产品版本</dt><dd>{{ requirement.product_version || '未指定' }}</dd></div>
            <div><dt><el-icon><CollectionTag /></el-icon>需求来源</dt><dd>{{ requirement.source === 'github' ? 'GitHub' : '需求平台' }}</dd></div>
            <div><dt><el-icon><Calendar /></el-icon>创建时间</dt><dd>{{ formatDateTime(requirement.created_at) }}</dd></div>
            <div><dt><el-icon><Clock /></el-icon>最后更新</dt><dd>{{ formatDateTime(requirement.updated_at) }}</dd></div>
          </dl>

          <a v-if="requirement.github_issue_url" class="github-link" :href="requirement.github_issue_url" target="_blank" rel="noopener noreferrer">
            <el-icon><Link /></el-icon>GitHub Issue #{{ requirement.github_issue_number }}<el-icon><TopRight /></el-icon>
          </a>
          <div v-if="requirement.github_pull_requests?.length" class="related-prs">
            <h2>关联 Pull Request</h2>
            <a v-for="pullRequest in requirement.github_pull_requests" :key="pullRequest.number"
              class="pr-link" :href="pullRequest.url" target="_blank" rel="noopener noreferrer">
              <span class="pr-title">#{{ pullRequest.number }} {{ pullRequest.title }}</span>
              <span class="pr-state" :class="`is-${pullRequest.state}`">
                {{ pullRequest.state === 'merged' ? '已合并' : pullRequest.state === 'open' ? (pullRequest.draft ? '草稿' : '进行中') : '已关闭' }}
              </span>
            </a>
          </div>

          <div class="detail-actions">
            <el-button v-if="canSupplement" @click="emit('supplement')">补充信息</el-button>
            <el-button @click="emit('continueAI')">复制给 AI 继续处理</el-button>
            <el-button v-if="hasReceipt" @click="emit('copyManagement')">保存修改入口</el-button>
            <el-button v-if="manager" :icon="Promotion" @click="emit('review')">提交审核</el-button>
          </div>
          <p v-if="hasReceipt" class="field-hint side-note">修改权限保存在此浏览器。换设备或清除浏览器数据前，请保存修改入口；持有链接的人可以修改此需求，请勿公开分享。</p>
          <p v-if="editReason" class="field-hint side-note">{{ editReason }}</p>
        </article>

        <article class="panel side-timeline">
          <h2>状态变化</h2>
          <div v-if="!history.length" class="field-hint">暂无状态记录</div>
          <div v-for="event in history" :key="event.id" class="timeline-item">
            <span class="timeline-dot"></span>
            <div class="timeline-copy">
              <strong>{{ historyLabel(event) }}</strong>
              <p>{{ event.actor_name }} · {{ formatDateTime(event.created_at) }}</p>
              <p v-if="event.reason" class="timeline-reason">{{ event.reason }}</p>
            </div>
          </div>
        </article>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  ArrowDown, ArrowLeft, Calendar, Check, Clock, CollectionTag, Edit, EditPen, Flag, Link,
  MagicStick, Promotion, Star, TopRight, User, View, Warning,
} from '@element-plus/icons-vue'
import { ElButton, ElIcon, ElInput, ElMessage, ElOption, ElSelect } from 'element-plus'
import MarkdownIt from 'markdown-it'
import type { Requirement, RequirementHistory, RequirementSupplement } from './api'
import { nextAction } from './feedbackExperience'
import { avatarColor, formatDateTime, priorityLabel, statusLabel, typeLabel } from './labels'
import { trailOf, trailStages } from './requirementTrail'
import DeliveryWorkspace from './DeliveryWorkspace.vue'
import { api } from './api'

type Attachment = NonNullable<Requirement['attachments']>[number]

const props = defineProps<{
  requirement: Requirement
  history: RequirementHistory[]
  manager: boolean
  canEdit?: boolean
  hasReceipt?: boolean
  editReason?: string
  canSupplement?: boolean
  supplements: RequirementSupplement[]
  supplementsError?: boolean
  canFollow: boolean
  canEditSummary: boolean
  userRole: string
}>()
const emit = defineEmits<{
  back: []
  copyLink: []
  copyManagement: []
  continueAI: []
  supplement: []
  follow: []
  edit: []
  status: []
  review: []
  download: [attachment: Attachment]
  refresh: []
}>()

const trail = computed(() => trailOf(props.requirement.status))

const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true })
markdown.renderer.rules.link_open = (tokens, index, options, _env, self) => {
  const token = tokens[index]
  if (!token) return ''
  token.attrSet('target', '_blank')
  token.attrSet('rel', 'noopener noreferrer')
  return self.renderToken(tokens, index, options)
}

const triageText = computed(() => String(
  props.requirement.confirmed_summary || props.requirement.triage?.problem_summary || props.requirement.triage?.summary || '分析已完成',
))
const confirmedFacts = computed(() => ((props.requirement.triage?.confirmed_facts as Array<Record<string, unknown>> | undefined) || []).map(item => String(item.statement || item.value || '')).filter(Boolean))
const acceptanceDraft = computed(() => (props.requirement.triage?.acceptance_draft as string[] | undefined) || [])
const openClarifications = computed(() => (props.requirement.clarifications || []).filter(item => item.status === 'open'))
const nextStep = computed(() => openClarifications.value.length ? '等待补充关键信息' : props.requirement.status === 'pending_review' ? '等待维护者审核' : statusLabel(props.requirement.status))
const summaryCorrection = ref('')
const answers = reactive<Record<string, string>>({})
const saving = ref(false)
watch(() => props.requirement.id, () => { summaryCorrection.value = props.requirement.confirmed_summary || '' })
async function saveSummary() {
  if (summaryCorrection.value.trim().length < 4) { ElMessage.error('请填写至少 4 个字符'); return }
  saving.value = true
  try { await api.correctSummary(props.requirement.id, summaryCorrection.value.trim(), props.requirement.state_version); ElMessage.success('摘要纠正已提交'); emit('refresh') }
  catch (error: any) { ElMessage.error(error?.response?.data?.msg || '提交失败') } finally { saving.value = false }
}
async function answer(questionId: string) {
  const value = (answers[questionId] || '').trim()
  if (!value) { ElMessage.error('请填写答案，也可以填写“不确定”'); return }
  saving.value = true
  try { await api.answerClarification(props.requirement.id, questionId, value, props.requirement.state_version); ElMessage.success('答案已提交'); emit('refresh') }
  catch (error: any) { ElMessage.error(error?.response?.data?.msg || '提交失败') } finally { saving.value = false }
}
const renderMarkdown = (value?: string) => markdown.render(value || '')
const formatBytes = (size: number) => size < 1024 * 1024 ? `${Math.ceil(size / 1024)}KB` : `${(size / 1024 / 1024).toFixed(1)}MB`
const historyLabel = (event: RequirementHistory) => {
  if (event.before && event.after && event.before !== event.after) return `状态由“${statusLabel(event.before)}”变为“${statusLabel(event.after)}”`
  if (event.action === 'requirement.created') return '需求已提交'
  if (event.action === 'requirement.updated') return '需求内容已更新'
  if (event.action === 'triage.completed') return 'AI 分析完成，进入待审核'
  if (event.after) return `状态更新为“${statusLabel(event.after)}”`
  return '需求有新动态'
}
</script>

<style scoped>
.detail-page { max-width: 1320px; margin: 0 auto; }
.detail-back {
  display: inline-flex; align-items: center; gap: 6px;
  margin: 0 0 16px; padding: 6px 12px 6px 8px;
  border: 1px solid transparent; border-radius: 9px;
  background: transparent; color: var(--ink-3);
  font-size: 12.5px; cursor: pointer;
  transition: background var(--dur) var(--ease), color var(--dur) var(--ease), border-color var(--dur) var(--ease);
}
.detail-back:hover { background: var(--surface); border-color: var(--line); color: var(--ink); }
.detail-back:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }

.detail-hero {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 26px; margin-bottom: 20px;
}
.dh-main { min-width: 0; flex: 1; }
.dh-eyebrow { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.dh-eyebrow .req-number {
  padding: 2px 9px; border-radius: 7px;
  background: var(--surface); border: 1px solid var(--line);
  color: var(--ink-3); font-size: 11px;
}
.detail-hero h1 {
  margin: 0 0 12px; max-width: 880px;
  font-size: 29px; line-height: 1.3; font-weight: 800; letter-spacing: -.03em;
  overflow-wrap: anywhere;
}
.detail-meta {
  display: flex; align-items: center; flex-wrap: wrap; gap: 7px;
  color: var(--ink-3); font-size: 12.5px;
}
.detail-meta strong { color: var(--ink-2); font-weight: 600; }
.detail-meta .dot { color: var(--ink-5); }
.meta-follow { display: inline-flex; align-items: center; gap: 4px; }
.meta-follow .el-icon { color: var(--accent); }
.dh-actions { display: flex; align-items: center; gap: 8px; flex: none; padding-top: 6px; }
.dh-actions .el-button { margin-left: 0; }
.dh-link { color: var(--ink-2); }

/* ---------------- 生命周期 ---------------- */
.trail-card {
  display: grid; grid-template-columns: minmax(0, 1fr) minmax(280px, 420px);
  gap: 22px; align-items: center;
  margin-bottom: 20px; padding: 18px 22px;
  border: 1px solid var(--line); border-radius: var(--r-lg);
  background:
    linear-gradient(120deg, color-mix(in srgb, var(--primary) 5%, var(--surface)), var(--surface) 46%);
  box-shadow: var(--shadow-xs);
}
.trail-steps { display: grid; grid-template-columns: repeat(5, 1fr); list-style: none; margin: 0; padding: 0; }
.trail-steps li { position: relative; display: grid; justify-items: center; gap: 7px; }
.trail-steps li::before {
  content: ""; position: absolute; top: 8px; left: -50%; width: 100%; height: 2px;
  background: var(--line-2);
}
.trail-steps li:first-child::before { display: none; }
.trail-steps li.done::before, .trail-steps li.now::before {
  background: linear-gradient(90deg, color-mix(in srgb, var(--primary) 42%, var(--line-2)), var(--primary));
}
.ts-dot {
  position: relative; z-index: 1;
  display: grid; place-items: center;
  width: 18px; height: 18px; border-radius: 50%;
  background: var(--surface); border: 2px solid var(--line-2);
  color: #fff;
  transition: all var(--dur) var(--ease);
}
.trail-steps li.done .ts-dot { background: var(--primary); border-color: var(--primary); }
.trail-steps li.now .ts-dot {
  background: var(--primary); border-color: var(--primary);
  box-shadow: 0 0 0 5px var(--primary-soft);
  animation: pulse-ring 2.4s ease-out infinite;
}
.trail-steps li.stopped .ts-dot { background: var(--ink-4); border-color: var(--ink-4); }
.ts-label { font-size: 11.5px; font-weight: 600; color: var(--ink-4); }
.trail-steps li.done .ts-label { color: var(--ink-2); }
.trail-steps li.now .ts-label { color: var(--primary); font-weight: 700; }
.trail-note {
  display: flex; align-items: flex-start; gap: 9px;
  padding: 11px 14px; border-radius: 12px;
  background: var(--primary-softer);
  border: 1px solid color-mix(in srgb, var(--primary) 14%, transparent);
  color: var(--ink-2);
}
.trail-note .el-icon { color: var(--primary); margin-top: 2px; flex: none; }
.trail-note p { font-size: 12.5px; line-height: 1.6; margin: 0; }
.trail-note strong { display: block; color: var(--primary-deep); font-size: 11px; letter-spacing: .06em; margin-bottom: 2px; }

/* ---------------- 布局 ---------------- */
.detail-layout { display: grid; grid-template-columns: minmax(0, 1fr) 330px; gap: 20px; align-items: start; }
.detail-main { display: grid; gap: 18px; min-width: 0; }
.detail-sidebar { display: grid; gap: 16px; min-width: 0; position: sticky; top: 22px; }

.detail-content { padding: 24px 26px; }
.content-block + .content-block { margin-top: 22px; padding-top: 20px; border-top: 1px solid var(--line); }
.detail-section-title { display: flex; align-items: center; gap: 10px; margin: 0 0 14px; font-size: 15px; font-weight: 700; }
.detail-section-icon {
  display: grid; place-items: center; flex: none;
  width: 26px; height: 26px; border-radius: 8px;
  background: var(--primary-soft); color: var(--primary);
  font-size: 11px; font-weight: 800;
}

.triage-box {
  margin-top: 22px; padding: 16px 18px;
  border-radius: 14px;
  background: linear-gradient(150deg, var(--primary-softer), var(--surface));
  border: 1px solid color-mix(in srgb, var(--primary) 14%, var(--line));
}
.triage-head { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 13px; color: var(--primary-deep); margin-bottom: 10px; }
.triage-orb {
  display: grid; place-items: center;
  width: 24px; height: 24px; border-radius: 8px;
  background: linear-gradient(135deg, var(--primary), var(--brand-teal));
  color: #fff;
}
.triage-orb.spinning { animation: spin 1.6s linear infinite; }
.triage-model { margin-left: auto; color: var(--ink-4); font-size: 11px; font-weight: 500; }
.triage-pending p { margin: 6px 0 0; color: var(--ink-3); font-size: 12.5px; line-height: 1.65; }
.analysis-list { margin-top: 14px; font-size: 12.5px; }
.analysis-list strong { color: var(--ink-2); }
.analysis-list ul { margin: 6px 0 0; padding-left: 18px; color: var(--ink-2); line-height: 1.7; }
.analysis-next { display: flex; gap: 10px; margin-top: 14px; font-size: 12.5px; }
.analysis-next span { color: var(--ink-2); }
.summary-correction { display: grid; gap: 8px; margin-top: 14px; }

.clarification-box {
  display: grid; gap: 14px; margin-top: 18px; padding: 16px;
  border: 1px solid color-mix(in srgb, var(--warning) 22%, var(--line));
  border-radius: 14px; background: var(--warning-soft);
}
.clarification-box > strong { font-size: 13px; color: var(--warning); }
.clarification-box article { display: grid; gap: 8px; }
.clarification-box p { margin: 0; font-size: 13.5px; line-height: 1.6; }
.clarification-box small { display: block; margin-top: 3px; color: var(--ink-3); font-size: 11.5px; }

.review-note, .log-panel, .attachments, .contact-box { margin-top: 18px; }
.review-note {
  padding: 13px 15px; border-radius: 12px;
  background: var(--surface-2); border: 1px solid var(--line);
}
.review-note > strong { font-size: 12.5px; }
.contact-box { padding: 12px 14px; border-radius: 10px; background: var(--warning-soft); color: var(--warning); font-size: 12.5px; }
.log-panel, .attachments { padding-top: 16px; border-top: 1px solid var(--line); }
.log-panel > strong, .attachments > strong { font-size: 12.5px; color: var(--ink-2); }
.log-text {
  margin: 8px 0 0; max-height: 240px; overflow: auto;
  padding: 12px; border-radius: 10px;
  background: var(--surface-2); border: 1px solid var(--line);
  white-space: pre-wrap; word-break: break-word;
  font-size: 11.5px; line-height: 1.6; color: var(--ink-2);
}
.attachments .file-row { margin-top: 6px; }

.supplement-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.supplement-empty { color: var(--ink-4); font-size: 12.5px; padding: 14px 0; }
.supplement-item {
  margin-top: 14px; padding: 14px 16px;
  border-radius: 12px; background: var(--surface-2);
  border: 1px solid var(--line);
}
.supplement-meta { display: flex; align-items: center; gap: 7px; font-size: 12.5px; }
.supplement-meta strong { font-size: 12.5px; }
.supplement-body { white-space: pre-wrap; overflow-wrap: anywhere; color: var(--ink-2); line-height: 1.7; margin: 8px 0 0; font-size: 13px; }

/* ---------------- 侧栏 ---------------- */
.side-status { padding: 18px; }
.status-fields { margin: 0; display: grid; gap: 2px; }
.status-fields > div {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 7px 0; font-size: 12.5px;
}
.status-fields > div + div { border-top: 1px dashed color-mix(in srgb, var(--line) 80%, transparent); }
.status-fields dt { display: flex; align-items: center; gap: 7px; color: var(--ink-3); }
.status-fields dt .el-icon { color: var(--ink-4); }
.status-fields dd { margin: 0; color: var(--ink-2); text-align: right; overflow-wrap: anywhere; }
.status-control {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 4px; border: 0; border-radius: 8px;
  background: transparent; color: var(--primary); cursor: pointer;
}
.status-control:not(:disabled):hover { background: var(--primary-soft); }
.status-control:disabled { cursor: default; }
.related-prs { margin-top: 16px; }
.related-prs h2 { margin: 0 0 8px; font-size: 12.5px; }
.pr-link {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 8px;
  padding: 8px 0; border-top: 1px solid var(--line);
  color: var(--ink-2); font-size: 12.5px;
}
.pr-link:hover .pr-title { color: var(--primary); text-decoration: underline; }
.pr-title { min-width: 0; overflow-wrap: anywhere; }
.pr-state { flex: none; padding: 1px 7px; border-radius: 999px; background: var(--surface-3); color: var(--ink-3); font-size: 10.5px; }
.pr-state.is-open { background: var(--success-soft); color: var(--success); }
.pr-state.is-merged { background: var(--violet-soft); color: var(--violet); }
.detail-actions { display: grid; gap: 8px; margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--line); }
.detail-actions .el-button { margin-left: 0; width: 100%; }
.side-note { margin-top: 10px; }

.side-timeline { padding: 18px; }
.side-timeline h2 { margin: 0 0 16px; font-size: 14px; }
.timeline-item { position: relative; display: flex; gap: 11px; padding: 0 0 16px; }
.timeline-item:not(:last-child)::before {
  content: ''; position: absolute; left: 4px; top: 14px; bottom: 0;
  width: 1px; background: var(--line);
}
.timeline-dot {
  position: relative; z-index: 1; flex: none;
  width: 9px; height: 9px; margin-top: 4px; border-radius: 50%;
  background: var(--surface); border: 2px solid var(--primary);
}
.timeline-item:first-child .timeline-dot { background: var(--primary); box-shadow: 0 0 0 3px var(--primary-soft); }
.timeline-copy strong { font-size: 12.5px; line-height: 1.45; font-weight: 600; }
.timeline-copy p { margin: 3px 0 0; color: var(--ink-4); font-size: 11.5px; line-height: 1.45; }
.timeline-copy .timeline-reason { color: var(--ink-2); }

.markdown-body { min-width: 0; color: var(--ink-2); font-size: 13.5px; line-height: 1.8; overflow-wrap: anywhere; }
.markdown-body.compact { font-size: 12.5px; }
.markdown-body :deep(:first-child) { margin-top: 0; }
.markdown-body :deep(:last-child) { margin-bottom: 0; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) { color: var(--ink); line-height: 1.4; }
.markdown-body :deep(h1) { font-size: 20px; padding-bottom: 8px; border-bottom: 1px solid var(--line); }
.markdown-body :deep(h2) { font-size: 16.5px; padding-bottom: 6px; border-bottom: 1px solid var(--line); }
.markdown-body :deep(h3) { font-size: 15px; }
.markdown-body :deep(a) { color: var(--primary); text-decoration: underline; text-underline-offset: 2px; }
.markdown-body :deep(blockquote) { margin: 12px 0; padding: 2px 14px; border-left: 3px solid var(--primary); color: var(--ink-3); background: var(--surface-2); border-radius: 0 8px 8px 0; }
.markdown-body :deep(code) { padding: 2px 5px; border-radius: 5px; background: var(--surface-3); color: var(--danger); font-size: 12px; }
.markdown-body :deep(pre) { max-width: 100%; padding: 14px; border-radius: 10px; background: #0f1523; color: #dbe3f0; overflow-x: auto; }
.markdown-body :deep(pre code) { padding: 0; background: transparent; color: inherit; }
.markdown-body :deep(img) { max-width: 100%; height: auto; border-radius: 10px; }
.markdown-body :deep(table) { display: block; max-width: 100%; border-collapse: collapse; overflow-x: auto; }
.markdown-body :deep(th), .markdown-body :deep(td) { padding: 7px 10px; border: 1px solid var(--line); }

@media (max-width: 1080px) {
  .trail-card { grid-template-columns: minmax(0, 1fr); gap: 16px; }
  .detail-layout { grid-template-columns: minmax(0, 1fr); }
  .detail-sidebar { position: static; grid-template-columns: 1fr 1fr; }
}
@media (max-width: 760px) {
  .detail-hero { display: grid; gap: 14px; }
  .detail-hero h1 { font-size: 22px; }
  .dh-actions { width: 100%; }
  .dh-actions .el-button { flex: 1; }
  .trail-card { padding: 16px; }
  .ts-label { font-size: 10.5px; }
  .detail-content { padding: 18px; }
  .detail-sidebar { grid-template-columns: minmax(0, 1fr); }
}
</style>