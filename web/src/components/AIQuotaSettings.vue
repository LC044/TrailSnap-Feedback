<template>
  <article class="panel settings-block" aria-label="对话限额设置">
    <div class="policy-head"><div><h2>对话限额</h2><p>每日额度 · 保存后立即生效</p></div><el-button :loading="loading" @click="load">刷新</el-button></div>
    <el-alert v-if="error" type="error" :closable="false" :title="error" />
    <el-form v-if="policy" label-position="top" @submit.prevent="save">
      <el-form-item label="个人限额方式"><el-radio-group v-model="policy.mode"><el-radio-button value="count">按次数</el-radio-button><el-radio-button value="tokens">按 Token</el-radio-button><el-radio-button value="both">同时限制</el-radio-button></el-radio-group></el-form-item>
      <div class="policy-grid">
        <fieldset v-for="group in groups" :key="group.key"><legend>{{ group.label }}</legend>
          <el-form-item v-if="policy.mode !== 'tokens'" label="每天最多对话次数"><el-input-number v-model="policy[group.count]" :min="0" :max="100000" controls-position="right" /></el-form-item>
          <el-form-item v-if="policy.mode !== 'count'" label="每天 Token 预算（M）"><el-input-number :model-value="policy[group.tokens] / 1000000" @update:model-value="setTokens(group.tokens, $event)" :min="0" :max="100" :step="0.001" :precision="3" controls-position="right" /></el-form-item>
        </fieldset>
        <fieldset><legend>全站保护（始终生效）</legend>
          <el-form-item label="全站每天最多次数"><el-input-number v-model="policy.global_daily" :min="0" :max="1000000" /></el-form-item>
          <el-form-item label="全站每天 Token 预算（M）"><el-input-number :model-value="policy.global_tokens / 1000000" @update:model-value="setTokens('global_tokens', $event)" :min="0" :max="1000" :step="0.001" :precision="3" /></el-form-item>
          <el-form-item label="每个 IP 每天最多次数"><el-input-number v-model="policy.ip_daily" :min="0" :max="1000000" /></el-form-item>
          <el-form-item label="最短发送间隔（秒）"><el-input-number v-model="policy.interval_seconds" :min="1" :max="3600" /></el-form-item>
        </fieldset>
      </div>
      <p class="policy-note">1 M = 1,000,000 Token，0 表示禁止使用。额度按请求与最大输出保守预留，失败不退还；修改额度保留已用记录。</p>
      <el-button type="primary" native-type="submit" :loading="saving">保存限额</el-button>
    </el-form>
  </article>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { call } from '../api/client'
type Policy = { mode:'count'|'tokens'|'both'; anonymous_daily:number; user_daily:number; anonymous_tokens:number; user_tokens:number; global_daily:number; global_tokens:number; ip_daily:number; interval_seconds:number }
const policy = ref<Policy>(), loading = ref(false), saving = ref(false), error = ref('')
const groups = [{ key:'anonymous', label:'匿名用户', count:'anonymous_daily', tokens:'anonymous_tokens' },{ key:'user', label:'登录用户（含管理员）', count:'user_daily', tokens:'user_tokens' }] as const
const reason = (e:any) => e?.response?.data?.msg || '无法保存，请稍后重试'
function setTokens(key:'anonymous_tokens'|'user_tokens'|'global_tokens', value:number|undefined) { if(policy.value && value !== undefined) policy.value[key] = Math.round(value * 1000000) }
async function load() { loading.value=true; try { policy.value=await call<Policy>('GET','/admin/ai-quota-policy'); error.value='' } catch(e){error.value=reason(e)} finally{loading.value=false} }
async function save(){saving.value=true; try{policy.value=await call<Policy>('PUT','/admin/ai-quota-policy',policy.value);error.value='';ElMessage.success('限额已保存')}catch(e){error.value=reason(e)}finally{saving.value=false}}
onMounted(load)
</script>
<style scoped>
.settings-block{margin-bottom:20px}.policy-head{display:flex;justify-content:space-between;gap:12px}.policy-head h2{margin:0;font-size:19px}.policy-head p,.policy-note{color:var(--rp-text-3);font-size:13px;line-height:1.7}.policy-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}fieldset{min-width:0;border:1px solid var(--rp-border);border-radius:12px;padding:16px}legend{color:var(--rp-text-2);font-size:14px}fieldset :deep(.el-input-number){width:100%}@media(max-width:900px){.policy-grid{grid-template-columns:1fr}}
</style>
