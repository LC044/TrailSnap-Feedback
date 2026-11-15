<template><section><div class="page-head"><h1>邮件通知</h1><el-button :loading="loading" @click="reload">刷新</el-button></div><MailSettings /><h2>投递记录</h2><el-alert v-if="error" type="error" :title="error" :closable="false" /><el-table :data="deliveries" v-loading="loading"><el-table-column prop="created_at" label="时间" min-width="190" /><el-table-column prop="kind" label="事件" /><el-table-column prop="status" label="状态" /><el-table-column prop="attempts" label="尝试次数" /><el-table-column prop="last_error" label="错误" min-width="220" /><el-table-column label="操作" width="100"><template #default="{row}"><el-button v-if="row.status === 'failed'" link type="primary" :disabled="retrying === row.id" @click="retry(row.id)">重试</el-button></template></el-table-column></el-table></section></template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import MailSettings from '../../components/MailSettings.vue'
import { collaboration, type Delivery } from '../../api/collaboration'
const deliveries = ref<Delivery[]>([]), error = ref(''), loading = ref(false), retrying = ref('')
async function reload(){loading.value=true;try{deliveries.value=await collaboration.deliveries();error.value=''}catch{error.value='无法读取投递记录，请重试'}finally{loading.value=false}}
async function retry(id:string){retrying.value=id;try{await collaboration.retryDelivery(id);await reload()}catch{error.value='重试失败，请刷新后再试'}finally{retrying.value=''}}
onMounted(reload)
</script>
