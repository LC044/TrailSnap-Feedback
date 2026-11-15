<template><section class="panel confirmation"><h1>{{ action === 'verify' ? '确认邮件订阅' : '取消邮件订阅' }}</h1><p>{{ result || '点击下方按钮确认操作。' }}</p><el-button v-if="!done" type="primary" :loading="busy" :disabled="!token" @click="confirm">{{ action === 'verify' ? '确认订阅' : '确认退订' }}</el-button></section></template>
<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { collaboration } from '../../api/collaboration'
const route = useRoute()
const action = String(route.params.action)
const token = new URLSearchParams(route.hash.slice(1)).get('token') || ''
const busy = ref(false), done = ref(false), result = ref(token ? '' : '链接缺少凭证，请从邮件重新打开。')
async function confirm() { busy.value = true; try { await collaboration.confirm(action, token); done.value = true; result.value = action === 'verify' ? '邮箱已确认，之后会收到此需求的进度与讨论通知。' : '已退订此需求的邮件通知。'; history.replaceState(null, '', location.pathname) } catch(e: any) { result.value = e?.response?.data?.msg || e?.response?.data?.detail || '操作失败，请重试' } finally { busy.value = false } }
</script>
<style scoped>.confirmation{max-width:640px;margin:40px auto;padding:28px}</style>
