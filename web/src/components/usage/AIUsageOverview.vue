<template>
  <section class="overview" aria-label="AI 运营概览">
    <header class="overview-head">
      <div><h2>运营概览</h2><p>按 UTC 自然日统计 · 含今天</p></div>
      <div class="controls">
        <el-select v-model="days" aria-label="时间范围" class="range"><el-option v-for="n in [7, 30, 90]" :key="n" :value="n" :label="`最近 ${n} 天`" /></el-select>
        <el-select v-model="source" aria-label="使用来源" class="range"><el-option v-for="item in sources" :key="item.key" :value="item.key" :label="item.label" /></el-select>
        <el-button :loading="loading" @click="load">刷新</el-button>
      </div>
    </header>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div v-loading="loading" class="overview-body">
      <template v-if="data">
        <dl class="kpis">
          <div v-for="item in kpis" :key="item.label" class="panel kpi">
            <dt>{{ item.label }}</dt><dd>{{ fmt(item.value) }}</dd><small>{{ item.note }}</small>
          </div>
        </dl>
        <div class="charts">
          <AIUsageTrend title="活跃与对话趋势" :rows="data.trend" :series="activitySeries" />
          <AIUsageTrend title="模型调用与 Token 趋势" :rows="data.trend" :series="tokenSeries" />
        </div>
        <div class="breakdowns">
          <article class="panel breakdown"><h3>按使用来源</h3>
            <el-table :data="data.sources" empty-text="暂无用量">
              <el-table-column label="来源" min-width="140"><template #default="{row}">{{ sourceLabel(row.kind) }}</template></el-table-column>
              <el-table-column label="对话轮次" min-width="95"><template #default="{row}">{{ fmt(row.turns) }}</template></el-table-column>
              <el-table-column label="调用 / 失败" min-width="110"><template #default="{row}">{{ fmt(row.requests) }} / {{ fmt(row.failed) }}</template></el-table-column>
              <el-table-column label="实际 Token" min-width="110"><template #default="{row}">{{ actual(row) }}</template></el-table-column>
            </el-table>
          </article>
          <article class="panel breakdown"><h3>按模型与连接 <small>最多显示 50 个</small></h3>
            <el-table :data="data.models" empty-text="所选范围暂无模型调用">
              <el-table-column label="模型 / 连接" min-width="145"><template #default="{row}"><strong>{{ row.model_name }}</strong><small class="connection">{{ row.connection_name }}</small></template></el-table-column>
              <el-table-column label="调用 / 失败" min-width="110"><template #default="{row}">{{ fmt(row.requests) }} / {{ fmt(row.failed) }}</template></el-table-column>
              <el-table-column label="输入 / 输出 Token" min-width="145"><template #default="{row}">{{ row.requests && row.requests === row.unreported && !(row.input_tokens + row.output_tokens) ? '未上报' : `${fmt(row.input_tokens)} / ${fmt(row.output_tokens)}` }}<small v-if="row.unreported" class="connection">{{ fmt(row.unreported) }} 次未完整上报</small></template></el-table-column>
              <el-table-column label="预留 Token" min-width="110"><template #default="{row}">{{ fmt(row.reserved_tokens) }}</template></el-table-column>
            </el-table>
          </article>
        </div>
        <p class="metric-note">{{ data.tracking_since ? `活跃与轮次从 ${data.tracking_since} 开始记录。` : '活跃与轮次尚无统计记录。' }}匿名按对话会话计，不等同于人数；已接收的首条请求和后续轮次均计入，重试单列。未归属调用包括后台任务、连接测试和旧记录。趋势里的 Token 只加总模型上报值，缺报日可能显示为 0，不是账单。</p>
      </template>
      <p v-else-if="loading" class="metric-note">正在读取用量…</p>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { loadAIOverview, type AIOverview, type UsageSource, type UsageCounts } from '../../api/aiUsage'
import AIUsageTrend from './AIUsageTrend.vue'

const days = ref(30), source = ref<UsageSource>('all'), data = ref<AIOverview | null>(null), loading = ref(false), error = ref('')
const sources: { key: UsageSource; label: string }[] = [
  {key:'all',label:'全部来源'}, {key:'intake',label:'AI 助手'}, {key:'requirement',label:'需求对话'}, {key:'background',label:'未归属调用'},
]
const sourceLabel = (key: UsageSource) => sources.find(item => item.key === key)?.label ?? key
const fmt = (value: number | string) => typeof value === 'number' ? value.toLocaleString('zh-CN') : value
const actual = (row: UsageCounts) => row.requests && row.requests === row.unreported && !(row.input_tokens + row.output_tokens) ? '未上报' : fmt(row.input_tokens + row.output_tokens)
const kpis = computed(() => {
  if (!data.value) return []
  const s = data.value.summary
  return [
    { label:'活跃账号', value:s.active_accounts, note:'区间内登录账号去重' },
    { label:'匿名会话', value:s.anonymous_sessions, note:'匿名会话去重，不估算人数' },
    { label:'活跃对话', value:s.conversations, note:'包含 AI 助手与需求对话' },
    { label:'对话轮次', value:s.turns, note:`另有 ${fmt(s.retries)} 次重试` },
    { label:'模型调用', value:s.requests, note:`${fmt(s.failed)} 次失败 · ${fmt(s.unreported)} 次缺报` },
    { label:'实际 Token', value:actual(s), note:`输入 ${fmt(s.input_tokens)} · 输出 ${fmt(s.output_tokens)}` },
    { label:'额度预留', value:s.reserved_tokens, note:'预算扣减，不等于实耗' },
  ]
})
const activitySeries = [{key:'turns', label:'对话轮次'}, {key:'conversations', label:'活跃对话'}, {key:'active_accounts', label:'活跃账号'}, {key:'anonymous_sessions', label:'匿名会话'}] as const
const tokenSeries = [{key:'total_tokens', label:'实际 Token'}, {key:'input_tokens', label:'输入 Token'}, {key:'output_tokens', label:'输出 Token'}, {key:'requests', label:'模型调用'}, {key:'failed', label:'失败调用'}] as const
let revision = 0
async function load() {
  const current = ++revision
  loading.value = true; error.value = ''; data.value = null
  try { const result = await loadAIOverview(days.value, source.value); if (current === revision) data.value = result }
  catch { if (current === revision) error.value = '无法读取 AI 运营概览，请刷新重试。' }
  finally { if (current === revision) loading.value = false }
}
watch([days, source], load, {immediate:true})
</script>
<style scoped>
.overview { margin-bottom: 24px; }.overview-head,.controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.overview-head{justify-content:space-between;margin-bottom:14px}.overview-head h2,.breakdown h3{margin:0}.overview-head p,.metric-note,.connection,small{color:var(--rp-text-3);font-size:12px}.overview-head p{margin:4px 0 0}.range{width:130px}.overview-body{min-height:86px}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(150px,100%),1fr));gap:10px;margin:0 0 12px}.kpi{padding:13px 14px;min-width:0}.kpi dt{font-size:13px;color:var(--rp-text-3)}.kpi dd{margin:5px 0;font-size:clamp(19px,2vw,27px);font-weight:700;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}.charts,.breakdowns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:12px}.breakdowns{grid-template-columns:minmax(0,.85fr) minmax(0,1.15fr)}.breakdown{padding:14px;min-width:0}.breakdown h3{margin-bottom:10px;font-size:16px}.connection{display:block;overflow-wrap:anywhere}.metric-note{line-height:1.65}.breakdown h3 small{font-weight:400}@media(max-width:900px){.charts,.breakdowns{grid-template-columns:minmax(0,1fr)}}@media(max-width:420px){.range{width:110px}.controls{gap:6px}}
</style>
