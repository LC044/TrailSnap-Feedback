<template>
  <article class="panel usage-settings" aria-label="模型 Token 用量">
    <div class="usage-head"><div><h2>模型用量</h2><p>最近 30 天 · 1 M = 1,000,000 Token</p></div><el-button :loading="loading" @click="load">刷新用量</el-button></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table :data="rows" v-loading="loading" empty-text="添加模型后可在此查看用量">
      <el-table-column label="模型 / API" min-width="210"><template #default="{row}"><strong>{{ row.model_name }}</strong><small>{{ row.connection_name }}</small><small v-if="row.unreported">{{ row.unreported }} 次未完整上报用量</small></template></el-table-column>
      <el-table-column prop="requests" label="调用" width="80" /><el-table-column prop="failed" label="失败" width="80" />
      <el-table-column label="输入（M）" width="120"><template #default="{row}">{{ m(row.input_tokens) }}</template></el-table-column>
      <el-table-column label="输出（M）" width="120"><template #default="{row}">{{ m(row.output_tokens) }}</template></el-table-column>
      <el-table-column label="今日合计（M）" width="150"><template #default="{row}">{{ m(row.today_tokens) }}</template></el-table-column>
      <el-table-column label="额度预留（M）" width="150"><template #default="{row}">{{ m(row.reserved_tokens) }}</template></el-table-column>
    </el-table>
    <p class="usage-note">输入、输出来自接口返回的 usage，包含缓存输入；未上报时不估算为实际用量。额度预留用于限制开销，与供应商账单可能不同。故障切换的每次调用均单独记录。</p>
  </article>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { aiUsage, type ModelUsage } from '../api/aiUsage'
const rows = ref<ModelUsage[]>([]), loading = ref(false), error = ref('')
const m = (value:number) => (value / 1000000).toLocaleString('zh-CN', { maximumFractionDigits: 6 })
async function load(){loading.value=true;try{rows.value=(await aiUsage.models()).models;error.value=''}catch{error.value='无法读取模型用量，请重试'}finally{loading.value=false}}
onMounted(load)
</script>
<style scoped>
.usage-settings{margin-bottom:20px}.usage-head{display:flex;justify-content:space-between;align-items:center;gap:16px}.usage-head h2{font-size:19px;margin:0}.usage-head p,.usage-note{color:var(--rp-text-3);font-size:12px;line-height:1.7}.usage-settings small{display:block;color:var(--rp-text-3);overflow-wrap:anywhere}
</style>
