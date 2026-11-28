<template>
  <div class="attachments">
    <ul v-if="modelValue.length" class="chips" aria-label="待发送附件">
      <li v-for="(item,i) in modelValue" :key="i">
        <img v-if="item.kind === 'image'" :src="`data:image/jpeg;base64,${item.data}`" alt="" />
        <span :title="item.name">{{ item.name }}</span>
        <button type="button" :aria-label="`移除 ${item.name}`" :disabled="disabled || busy" @click="remove(i)">×</button>
      </li>
    </ul>
    <div class="picker">
      <input ref="imageInput" type="file" :accept="IMAGE_TYPES" multiple hidden @change="pick($event, 'image')" />
      <input ref="fileInput" type="file" :accept="TEXT_EXTENSIONS" multiple hidden @change="pick($event, 'text')" />
      <el-button size="small" :icon="Picture" :disabled="disabled || busy || !canImage || imageCount >= MAX_IMAGES" @click="imageInput?.click()">图片</el-button>
      <el-button size="small" :icon="Paperclip" :disabled="disabled || busy || fileCount >= MAX_FILES" @click="fileInput?.click()">文件</el-button>
      <small v-if="imageCount">{{ imageCount }} / {{ MAX_IMAGES }} 张</small>
      <small v-if="busy" role="status">正在读取附件…</small>
      <small v-else-if="!canImage">{{ capabilityKnown ? '当前模型未启用图片输入' : '正在检查图片支持' }}</small>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <details><summary>附件格式与隐私</summary><p>每条消息最多 5 张 JPG、PNG 或 WebP 图片，可另附最多 3 个文本文件；图片会压缩。支持 UTF-8 的 TXT、LOG、MD、CSV、JSON、XML、YAML，合计不超过 6 KB。附件会发送给模型处理，不会自动公开或作为原文件保存。文字问答仅供平台管理员查阅。请先移除密钥和个人信息。</p></details>
  </div>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { Paperclip, Picture } from '@element-plus/icons-vue'
import { type ChatAttachment, IMAGE_TYPES, MAX_FILES, MAX_IMAGES, MAX_TEXT_BYTES, TEXT_EXTENSIONS, readChatAttachment } from '../chatAttachments'

const props = defineProps<{modelValue:ChatAttachment[];disabled:boolean;canImage:boolean;capabilityKnown:boolean}>()
const emit = defineEmits<{'update:modelValue':[value:ChatAttachment[]];busy:[value:boolean]}>()
const busy = ref(false), error = ref(''), imageInput = ref<HTMLInputElement>(), fileInput = ref<HTMLInputElement>()
const imageCount = computed(() => props.modelValue.filter(item => item.kind === 'image').length)
const fileCount = computed(() => props.modelValue.length - imageCount.value)
function remove(i:number) { emit('update:modelValue',props.modelValue.filter((_, index) => index !== i)); error.value = '' }
async function pick(event:Event, kind:ChatAttachment['kind']) {
  const input = event.target as HTMLInputElement, files = [...(input.files || [])]
  input.value = ''
  if (props.disabled || busy.value || !files.length) return
  if (kind === 'image' && !props.canImage) return
  if (kind === 'image' && imageCount.value + files.length > MAX_IMAGES) { error.value = '每条消息最多添加 5 张照片'; return }
  if (kind === 'text' && fileCount.value + files.length > MAX_FILES) { error.value = '每条消息最多添加 3 个文本文件'; return }
  busy.value = true; emit('busy', true); error.value = ''
  try {
    const existing = props.modelValue.filter(item => item.kind === 'text').reduce((n,item) => n + atob(item.data).length, 0)
    if (kind === 'text' && existing + files.reduce((n,file) => n+file.size,0) > MAX_TEXT_BYTES) throw new Error('文本附件合计不能超过 6 KB，请截取相关内容')
    const items: ChatAttachment[] = []
    for (const file of files) items.push(await readChatAttachment(file, kind))
    emit('update:modelValue',[...props.modelValue,...items])
  } catch (e) { error.value = e instanceof Error ? e.message : '无法读取附件' }
  finally { busy.value = false; emit('busy', false) }
}
</script>
<style scoped>
.attachments{min-width:0;font-size:12px}.picker,.chips{display:flex;align-items:center;flex-wrap:wrap;gap:6px}.picker .el-button{margin:0}.picker small,details{color:var(--rp-text-3)}.chips{list-style:none;padding:0;margin:0 0 5px}.chips li{display:flex;align-items:center;gap:5px;border:1px solid var(--rp-border);border-radius:6px;padding:2px 5px;max-width:100%}.chips span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:160px}.chips img{width:22px;height:22px;object-fit:cover;border-radius:3px}.chips button{border:0;background:none;color:inherit;cursor:pointer;font-size:17px}.error{color:var(--danger);margin:3px 0}details{margin-top:3px}details p{margin:4px 0;line-height:1.5}summary{cursor:pointer}
</style>
