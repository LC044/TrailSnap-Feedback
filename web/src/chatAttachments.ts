export type ChatAttachment = { kind: 'image' | 'text'; name: string; data: string }
export const TEXT_EXTENSIONS = '.txt,.log,.md,.csv,.json,.xml,.yaml,.yml'
export const IMAGE_TYPES = 'image/jpeg,image/png,image/webp'
export const MAX_IMAGES = 5
export const MAX_FILES = 3
export const MAX_TEXT_BYTES = 6000
const MAX_IMAGE_BYTES = 36000

function bytesToBase64(bytes: Uint8Array) {
  let raw = ''
  for (let i = 0; i < bytes.length; i += 4096) raw += String.fromCharCode(...bytes.subarray(i, i + 4096))
  return btoa(raw)
}

async function compressImage(file: File) {
  if (file.size > 8 * 1024 * 1024) throw new Error('原图不能超过 8 MB')
  const image = await createImageBitmap(file).catch(() => { throw new Error('图片无法读取，请重新选择') })
  try {
    if (image.width * image.height > 32_000_000) throw new Error('图片像素过多，请先裁剪')
    const canvas = document.createElement('canvas'), ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('浏览器无法处理图片')
    for (const maxEdge of [1200, 1000, 800, 640, 480, 360]) {
      const scale = Math.min(1, maxEdge / Math.max(image.width, image.height))
      canvas.width = Math.max(1, Math.round(image.width * scale)); canvas.height = Math.max(1, Math.round(image.height * scale))
      ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.drawImage(image, 0, 0, canvas.width, canvas.height)
      for (const quality of [.84, .72, .58]) {
        const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/jpeg', quality))
        if (blob?.type === 'image/jpeg' && blob.size <= MAX_IMAGE_BYTES) return bytesToBase64(new Uint8Array(await blob.arrayBuffer()))
      }
    }
    throw new Error('图片压缩后仍然过大，请先裁剪')
  } finally { image.close() }
}

export async function readChatAttachment(file: File, kind: ChatAttachment['kind']): Promise<ChatAttachment> {
  if (kind === 'image') {
    if (!IMAGE_TYPES.split(',').includes(file.type)) throw new Error('仅支持 JPG、PNG、WebP 图片')
    return {kind, name:file.name.slice(0, 140), data:await compressImage(file)}
  }
  const ext = file.name.lastIndexOf('.')
  if (ext < 0 || !TEXT_EXTENSIONS.split(',').includes(file.name.slice(ext).toLowerCase())) throw new Error('请选择 TXT、LOG、Markdown、CSV、JSON、XML 或 YAML 文件')
  if (!file.size || file.size > MAX_TEXT_BYTES) throw new Error('请选择非空文本文件，合计不超过 6 KB')
  const bytes = new Uint8Array(await file.arrayBuffer())
  try { new TextDecoder('utf-8', {fatal:true}).decode(bytes) } catch { throw new Error('文本文件须使用 UTF-8 编码') }
  return {kind, name:file.name.slice(0, 140), data:bytesToBase64(bytes)}
}
