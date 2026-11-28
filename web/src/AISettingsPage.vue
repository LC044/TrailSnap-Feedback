<template>
  <section>
    <div class="page-head">
      <div class="page-head-left">
        <div class="page-head-icon"><el-icon :size="23"><MagicStick /></el-icon></div>
        <div>
          <h1>AI 模型设置</h1>
          <p class="sub">集中管理模型连接，并按任务配置主模型与备用模型。</p>
          <p class="desc">密钥加密存储，页面不回显；修改后新的分析任务立即生效。</p>
        </div>
      </div>
      <div class="page-head-actions"><el-button :loading="loading" @click="load">刷新</el-button></div>
    </div>

    <el-alert v-if="settings?.legacy_environment_configured" type="info" :closable="false" show-icon title="检测到环境变量兼容配置">
      未保存任务路由时，后台需求分诊仍使用 RP_AI_API_URL / RP_AI_MODEL。保存路由后以页面配置为准。
    </el-alert>

    <AIQuotaSettings />
    <router-link class="ai-usage-link" :to="{ name: 'ai-usage' }">查看 AI 用量与对话 →</router-link>
    <el-alert type="info" :closable="false" title="模型接口配置">
      请配置兼容 Messages 协议的接口，测试连接会实际调用模型。
    </el-alert>
    <article class="panel settings-block">
      <h2>添加模型连接</h2>
      <el-form label-position="top" @submit.prevent="createConnection">
        <div class="connection-grid">
          <el-form-item label="连接名称"><el-input v-model="newConnection.name" placeholder="例如 OpenAI 主连接" /></el-form-item>
          <el-form-item label="接口地址"><el-input v-model="newConnection.api_base" placeholder="https://api.deepseek.com" /></el-form-item>
          <el-form-item label="API Key"><el-input v-model="newConnection.api_key" type="password" show-password autocomplete="new-password" placeholder="本地模型可留空" /></el-form-item>
          <el-form-item label="超时（秒）"><el-input-number v-model="newConnection.timeout_seconds" :min="3" :max="180" /></el-form-item>
        </div>
        <el-button type="primary" native-type="submit" :loading="saving">添加连接</el-button>
      </el-form>
    </article>

    <div class="connection-list">
      <article v-for="connection in settings?.connections || []" :key="connection.id" class="panel settings-block">
        <div class="block-head">
          <div><h2>{{ connection.name }}</h2><p>{{ connection.provider }} · {{ connection.models.length }} 个模型</p></div>
          <el-switch v-model="connection.enabled" active-text="启用" @change="saveConnection(connection)" />
        </div>
        <div class="connection-grid">
          <el-form-item label="连接名称"><el-input v-model="connection.name" /></el-form-item>
          <el-form-item label="接口地址"><el-input v-model="connection.api_base" /></el-form-item>
          <el-form-item :label="`API Key ${connection.api_key_hint || '未设置'}`">
            <el-input v-model="connectionKeys[connection.id]" type="password" show-password autocomplete="new-password" placeholder="留空表示不修改" />
          </el-form-item>
          <el-form-item label="超时（秒）"><el-input-number v-model="connection.timeout_seconds" :min="3" :max="180" /></el-form-item>
        </div>
        <div class="actions">
          <el-button :loading="saving" @click="saveConnection(connection)">保存连接</el-button>
          <el-button :disabled="!connection.models.length" @click="testConnection(connection)">测试连接</el-button>
          <el-button v-if="connection.has_api_key" @click="clearConnectionKey(connection)">清除密钥</el-button>
          <el-button type="danger" plain @click="removeConnection(connection)">删除</el-button>
        </div>

        <div class="models">
          <div class="models-head"><h3>模型</h3><span>配置模型支持的思考等级；仅在上游 Messages 接口支持视觉输入时勾选「图片输入」，并把该模型加入需求分诊路由。</span></div>
          <div v-for="model in connection.models" :key="model.id" class="model-row">
            <el-input v-model="model.display_name" placeholder="显示名称" />
            <el-input v-model="model.model_name" placeholder="上游模型名" />
            <el-input-number v-model="model.context_window" :min="1024" :max="10000000" placeholder="上下文" />
            <el-select v-model="model.reasoning_levels" multiple collapse-tags placeholder="支持的思考等级">
              <el-option v-for="level in reasoningOptions" :key="level" :label="reasoningLabel(level)" :value="level" />
            </el-select>
            <div class="model-capabilities"><el-checkbox v-model="model.supports_json_mode">JSON Mode</el-checkbox><el-checkbox v-model="model.supports_vision">图片输入</el-checkbox></div>
            <el-switch v-model="model.enabled" active-text="启用" />
            <div class="row-actions"><el-button size="small" @click="saveModel(model)">保存</el-button><el-button size="small" type="danger" link @click="removeModel(model)">删除</el-button></div>
          </div>
          <div class="model-row add-model">
            <el-input v-model="modelDraft(connection.id).display_name" placeholder="显示名称" />
            <el-input v-model="modelDraft(connection.id).model_name" placeholder="模型名，例如 gpt-5-mini" />
            <el-input-number v-model="modelDraft(connection.id).context_window" :min="1024" :max="10000000" placeholder="上下文" />
            <el-select v-model="modelDraft(connection.id).reasoning_levels" multiple collapse-tags placeholder="支持的思考等级">
              <el-option v-for="level in reasoningOptions" :key="level" :label="reasoningLabel(level)" :value="level" />
            </el-select>
            <div class="model-capabilities"><el-checkbox v-model="modelDraft(connection.id).supports_json_mode">JSON Mode</el-checkbox><el-checkbox v-model="modelDraft(connection.id).supports_vision">图片输入</el-checkbox></div>
            <span></span>
            <el-button type="primary" plain @click="addModel(connection.id)">添加模型</el-button>
          </div>
        </div>
      </article>
    </div>

    <article class="panel settings-block">
      <h2>任务模型路由</h2>
      <p class="route-help">第一个为主模型，故障时按顺序切换模型或 API；单次最多尝试前三个模型，共享调用与 Token 预算。达到平台限额时停止切换。</p>
      <div v-for="route in settings?.routes || []" :key="route.task_type" class="route-row">
        <div><strong>{{ route.label }}</strong><p>{{ route.description }}<span v-if="route.source === 'environment'"> · 当前使用环境变量</span></p></div>
        <el-switch v-model="route.enabled" />
        <el-select v-model="route.model_ids" multiple filterable placeholder="依次选择主模型和备用模型">
          <el-option v-for="option in modelOptions" :key="option.id" :label="option.label" :value="option.id" :disabled="!option.enabled" />
        </el-select>
        <el-select v-model="route.reasoning_effort" placeholder="思考等级">
          <el-option v-for="level in routeReasoningLevels(route)" :key="level" :label="reasoningLabel(level)" :value="level" />
        </el-select>
        <el-button @click="saveRoute(route)">保存路由</el-button>
      </div>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import AIQuotaSettings from './components/AIQuotaSettings.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, type AIConnection, type AIModel, type AISettings, type AITaskRoute } from './api'

const loading = ref(false), saving = ref(false)
const settings = ref<AISettings | null>(null)
const connectionKeys = reactive<Record<string, string>>({})
const reasoningOptions = ['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max']
const reasoningLabel = (level: string) => ({ none: '关闭', minimal: '最低', low: '低', medium: '中', high: '高', xhigh: '超高', max: '最大' }[level] || level)
const modelDrafts = reactive<Record<string, { model_name: string; display_name: string; context_window?: number; supports_json_mode: boolean; supports_vision: boolean; reasoning_levels: string[] }>>({})
const newConnection = reactive({ name: '', api_base: '', api_key: '', timeout_seconds: 45 })
const emptyModel = () => ({ model_name: '', display_name: '', context_window: 128000, supports_json_mode: true, supports_vision: false, reasoning_levels: ['none', 'low', 'medium', 'high'] })
function modelDraft(connectionId: string) { return modelDrafts[connectionId] ||= emptyModel() }
const modelOptions = computed(() => (settings.value?.connections || []).flatMap(connection => connection.models.map(model => ({
  id: model.id, label: `${connection.name} / ${model.display_name || model.model_name}`,
  enabled: connection.enabled && model.enabled,
}))))
function routeReasoningLevels(route: AITaskRoute) {
  const models = (settings.value?.connections || []).flatMap(connection => connection.models).filter(model => route.model_ids.includes(model.id))
  if (!models.length) return ['none']
  return reasoningOptions.filter(level => models.every(model => (model.reasoning_levels || ['none']).includes(level)))
}

function message(error: any) { return error?.response?.data?.msg || error?.response?.data?.detail || '操作失败' }
async function load() {
  loading.value = true
  try {
    settings.value = await api.aiSettings()
    for (const connection of settings.value.connections) {
      connectionKeys[connection.id] = ''
      modelDrafts[connection.id] ||= emptyModel()
    }
  } catch (error) { ElMessage.error(message(error)) } finally { loading.value = false }
}
async function createConnection() {
  saving.value = true
  try {
    await api.createAIConnection({ ...newConnection, provider: 'openai_compatible', enabled: true, priority: 100 })
    Object.assign(newConnection, { name: '', api_base: '', api_key: '', timeout_seconds: 45 })
    ElMessage.success('模型连接已添加'); await load()
  } catch (error) { ElMessage.error(message(error)) } finally { saving.value = false }
}
async function saveConnection(connection: AIConnection) {
  saving.value = true
  try {
    await api.updateAIConnection(connection.id, { name: connection.name, api_base: connection.api_base,
      api_key: connectionKeys[connection.id] || undefined, enabled: connection.enabled,
      timeout_seconds: connection.timeout_seconds, priority: connection.priority })
    connectionKeys[connection.id] = ''; ElMessage.success('连接已保存'); await load()
  } catch (error) { ElMessage.error(message(error)) } finally { saving.value = false }
}
async function removeConnection(connection: AIConnection) {
  try { await ElMessageBox.confirm(`删除连接“${connection.name}”及其全部模型？相关任务路由会自动清理。`, '删除模型连接'); await api.deleteAIConnection(connection.id); await load() }
  catch (error) { if (error !== 'cancel') ElMessage.error(message(error)) }
}
async function clearConnectionKey(connection: AIConnection) {
  try { await ElMessageBox.confirm('清除后，该连接只能访问无需鉴权的本地服务。', '清除 API Key'); await api.updateAIConnection(connection.id, { clear_api_key: true }); ElMessage.success('API Key 已清除'); await load() }
  catch (error) { if (error !== 'cancel') ElMessage.error(message(error)) }
}
async function addModel(connectionId: string) {
  const draft = modelDraft(connectionId)
  try { await api.createAIModel(connectionId, { ...draft, enabled: true }); modelDrafts[connectionId] = emptyModel(); ElMessage.success('模型已添加'); await load() }
  catch (error) { ElMessage.error(message(error)) }
}
async function saveModel(model: AIModel) {
  try { await api.updateAIModel(model.id, { model_name: model.model_name, display_name: model.display_name,
    enabled: model.enabled, supports_json_mode: model.supports_json_mode, supports_vision: model.supports_vision, context_window: model.context_window || null,
    reasoning_levels: model.reasoning_levels.length ? model.reasoning_levels : ['none'] }); ElMessage.success('模型已保存'); await load() }
  catch (error) { ElMessage.error(message(error)) }
}
async function removeModel(model: AIModel) {
  try { await ElMessageBox.confirm(`删除模型“${model.display_name || model.model_name}”？`, '删除模型'); await api.deleteAIModel(model.id); await load() }
  catch (error) { if (error !== 'cancel') ElMessage.error(message(error)) }
}
async function testConnection(connection: AIConnection) {
  try { const result = await api.testAIConnection(connection.id); result.available ? ElMessage.success(`连接成功：${result.response || 'OK'}`) : ElMessage.error(`连接失败：${result.error}`) }
  catch (error) { ElMessage.error(message(error)) }
}
async function saveRoute(route: AITaskRoute) {
  try { await api.updateAITaskRoute(route.task_type, { enabled: route.enabled, model_ids: route.model_ids, reasoning_effort: route.reasoning_effort }); ElMessage.success(`${route.label}路由已保存`); await load() }
  catch (error) { ElMessage.error(message(error)) }
}
onMounted(load)
</script>

<style scoped>
.model-capabilities { display:flex; flex-direction:column; }
.model-capabilities :deep(.el-checkbox) { height:24px; margin-right:0; }
.ai-usage-link { display: inline-block; margin: 0 0 16px; color: var(--rp-primary); }
.sub { color:var(--ink-3); }
.settings-block { margin-top:18px; padding:20px; }.settings-block h2 { margin:0 0 14px; font-size:16px; }
.connection-list { display:grid; gap:16px; }.connection-grid { display:grid; grid-template-columns:1fr 2fr 1.5fr 150px; gap:12px; }
.block-head,.models-head { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }.block-head h2,.models-head h3 { margin:0; }.block-head p,.models-head span,.route-help,.route-row p { color:var(--rp-text-3); font-size:13px; }
.actions,.row-actions { display:flex; flex-wrap:wrap; gap:8px; }.models { margin-top:20px; border-top:1px solid var(--rp-border); padding-top:16px; }
.model-row { display:grid; grid-template-columns:1fr 1.3fr 140px minmax(170px,1fr) 110px 90px auto; gap:10px; align-items:center; margin-top:10px; }.add-model { padding-top:10px; border-top:1px dashed var(--rp-border); }
.route-row { display:grid; grid-template-columns:minmax(190px,1fr) 60px minmax(260px,2fr) 130px auto; gap:14px; align-items:center; padding:14px 0; border-top:1px solid var(--rp-border); }.route-row p { margin:4px 0 0; }
@media (max-width:900px) { .connection-grid,.model-row,.route-row { grid-template-columns:1fr; }.model-row { padding:12px 0; border-top:1px solid var(--rp-border); }.route-row { align-items:stretch; } }
</style>
