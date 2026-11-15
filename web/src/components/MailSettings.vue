<template>
  <section class="panel mail-settings" v-loading="loading" aria-label="发件邮箱设置">
    <div class="settings-head"><div><h2>发件邮箱</h2><p>轮换发送 · 失败自动切换 · 每个账号独立限额</p></div><el-button :disabled="loading || saving || accounts.length >= 8" @click="add">添加邮箱</el-button></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-empty v-if="!accounts.length && !loading" description="添加一个发件邮箱，开启进度通知" :image-size="64" />
    <el-collapse v-model="expanded">
      <el-collapse-item v-for="(account, index) in accounts" :key="account.id || `new-${index}`" :name="String(index)">
        <template #title><div class="account-title"><strong>{{ account.name || '新邮箱' }}</strong><span>{{ account.sender || '待配置' }}</span><el-tag size="small" :type="account.enabled ? 'success' : 'info'">{{ account.enabled ? '启用' : '停用' }}</el-tag><small v-if="account.id">今日 {{ account.used_today || 0 }} / {{ account.daily_limit }}</small></div></template>
        <el-form label-position="top" class="account-form" @submit.prevent>
          <el-form-item label="名称"><el-input v-model="account.name" maxlength="60" placeholder="例如：通知邮箱 1" /></el-form-item>
          <el-form-item label="发件地址"><el-input v-model="account.sender" type="email" placeholder="name@qq.com" autocomplete="off" /></el-form-item>
          <el-form-item label="SMTP 服务器"><el-input v-model="account.host" placeholder="smtp.qq.com" /></el-form-item>
          <div class="transport"><el-form-item label="端口"><el-input-number v-model="account.port" :min="1" :max="65535" controls-position="right" /></el-form-item><el-form-item label="加密方式"><el-select v-model="account.tls"><el-option label="SSL / TLS" value="ssl" /><el-option label="STARTTLS" value="starttls" /><el-option label="不加密" value="none" /></el-select></el-form-item></div>
          <el-form-item label="登录账号"><el-input v-model="account.username" autocomplete="off" placeholder="通常与发件地址相同" /></el-form-item>
          <el-form-item label="授权码 / 密码"><el-input v-model="account.password" type="password" show-password autocomplete="new-password" :placeholder="account.has_password ? '已保存，留空保持原值' : '输入邮箱授权码'" /></el-form-item>
          <el-form-item label="每日最多尝试发送"><el-input-number v-model="account.daily_limit" :min="1" :max="10000" controls-position="right" /></el-form-item>
          <div class="account-actions"><el-switch v-model="account.enabled" active-text="启用" /><el-button type="danger" link @click="accounts.splice(index, 1)">移除此邮箱</el-button></div>
        </el-form>
      </el-collapse-item>
    </el-collapse>
    <div class="save-row"><span>最多 8 个账号；全部不可用时进入自动重试。</span><el-button type="primary" :loading="saving" :disabled="loading || !!loadFailed" @click="save">保存邮件配置</el-button></div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { mailSettings, type MailAccount } from '../api/mailSettings'
const accounts = ref<MailAccount[]>([]), expanded = ref<string[]>([])
const loading = ref(false), saving = ref(false), error = ref(''), loadFailed = ref(false)
function add() { accounts.value.push({ name: '', host: 'smtp.qq.com', port: 465, sender: '', username: '', tls: 'ssl', enabled: true, daily_limit: 100 }); expanded.value = [String(accounts.value.length - 1)] }
async function load() {
  loading.value = true
  try { accounts.value = (await mailSettings.get()).accounts; loadFailed.value = false; error.value = '' } catch { error.value = '无法读取邮件设置，请刷新重试'; loadFailed.value = true } finally { loading.value = false }
}
async function save() {
  saving.value = true; error.value = ''
  try { accounts.value = (await mailSettings.save(accounts.value)).accounts; ElMessage.success('邮件配置已保存') }
  catch (e: any) { error.value = typeof e?.response?.data?.msg === 'string' ? e.response.data.msg : '保存失败，请检查邮箱地址、服务器和授权码' }
  finally { saving.value = false }
}
onMounted(load)
</script>

<style scoped>
.mail-settings{margin-bottom:24px;padding:24px}.settings-head{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:16px}h2{margin:0;font-size:18px}p,.save-row span{font-size:12px;color:var(--rp-text-3)}p{margin:8px 0 0}.account-title{display:flex;gap:12px;align-items:center;flex-wrap:wrap;line-height:1.6;padding:12px 0}.account-title span,.account-title small{color:var(--rp-text-2)}.account-form{display:grid;grid-template-columns:1fr 1fr;gap:0 20px;padding:12px 0}.transport{display:grid;grid-template-columns:1fr 1fr;gap:12px}.transport :deep(.el-input-number),.transport :deep(.el-select){width:100%}.account-actions,.save-row{display:flex;justify-content:space-between;align-items:center;gap:16px}.save-row{margin-top:20px}.account-actions{align-self:center}.settings-head .el-button,.save-row .el-button{min-height:44px}
@media(max-width:650px){.mail-settings{padding:16px}.account-form{grid-template-columns:1fr}.save-row{align-items:stretch;flex-direction:column}.account-title{gap:8px}.account-title>span{font-size:12px;overflow-wrap:anywhere}}
</style>
