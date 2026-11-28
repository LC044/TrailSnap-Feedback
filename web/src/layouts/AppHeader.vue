<template>
  <!-- ===================== 桌面：左侧导航栏 ===================== -->
  <header class="topbar rail" :class="{ 'rail-collapsed': collapsed }">
    <div class="rail-head">
      <button class="brand" type="button" aria-label="行影集需求管理平台" @click="go(items[0]?.key ?? 'assistant')">
        <img :src="logoUrl" alt="" />
        <span class="brand-copy"><strong>行影集</strong><small>需求管理平台</small></span>
      </button>
      <button class="rail-collapse" type="button" :aria-label="collapsed ? '展开导航' : '折叠导航'"
        :title="collapsed ? '展开导航' : '折叠导航'" :aria-expanded="!collapsed" @click="$emit('toggle')">
        <el-icon :size="16"><Expand v-if="collapsed" /><Fold v-else /></el-icon>
      </button>
    </div>

    <button class="cmdk-trigger" type="button" aria-label="打开命令面板搜索页面与需求" @click="$emit('command')">
      <el-icon :size="15"><Search /></el-icon>
      <span>搜索页面、需求…</span>
      <kbd>{{ shortcut }}</kbd>
    </button>

    <nav ref="navElement" class="rail-nav" aria-label="主导航">
      <div v-for="group in groups" :key="group.label" class="nav-group">
        <p class="nav-group-label">{{ group.label }}</p>
        <button v-for="item in group.items" :key="item.key" type="button" class="nav-item"
          :class="{ active: active === item.key }" :aria-current="active === item.key ? 'page' : undefined"
          :title="collapsed ? item.label : undefined" :aria-label="collapsed ? item.label : undefined" @click="go(item.key)">
          <span class="nav-ico"><el-icon :size="18"><component :is="item.icon" /></el-icon></span>
          <span class="nav-label">{{ item.label }}</span>
          <span v-if="badges?.[item.key]" class="nav-badge">{{ badges[item.key] }}</span>
        </button>
      </div>
    </nav>

    <div class="rail-foot">
      <div class="rail-tools">
        <button class="rail-tool" type="button" :aria-label="isDark ? '切换到浅色主题' : '切换到深色主题'"
          :title="isDark ? '浅色主题' : '深色主题'" @click="toggleTheme">
          <el-icon :size="16"><Sunny v-if="isDark" /><Moon v-else /></el-icon>
          <span>{{ isDark ? '浅色' : '深色' }}</span>
        </button>
        <button class="rail-tool" type="button" aria-label="通知" @click="$emit('notification')">
          <el-icon :size="16"><Bell /></el-icon>
          <span>通知</span>
        </button>
      </div>

      <el-dropdown v-if="user" trigger="click" placement="top-start" @command="$emit('user-command', $event)">
        <button class="user-card" type="button">
          <span class="avatar" :style="{ width: '32px', height: '32px', fontSize: '13px', ...avatarColor(user.username) }">{{ user.username.slice(0, 1) }}</span>
          <span class="user-meta"><strong>{{ user.username }}</strong><small>{{ roleLabel(user.role) }}</small></span>
          <el-icon :size="13"><ArrowUp /></el-icon>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="mine">我的需求</el-dropdown-item>
            <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <button v-else class="primary-action rail-login" type="button" aria-label="登录或注册" @click="$emit('login')">
        <el-icon :size="15"><User /></el-icon><span>登录 / 注册</span>
      </button>
    </div>
  </header>

  <!-- ===================== 移动端：顶栏 + 底栏 ===================== -->
  <div class="mobile-chrome">
    <div class="mbar">
      <button class="mbar-brand" type="button" aria-label="返回首页" @click="go(items[0]?.key ?? 'assistant')">
        <img :src="logoUrl" alt="" />
        <span><strong>行影集</strong><small>需求管理平台</small></span>
      </button>
      <div class="mbar-actions">
        <button class="icon-btn" type="button" aria-label="搜索" @click="$emit('command')"><el-icon :size="18"><Search /></el-icon></button>
        <button class="icon-btn" type="button" aria-label="通知" @click="$emit('notification')"><el-icon :size="18"><Bell /></el-icon></button>
        <el-dropdown v-if="user" trigger="click" @command="$emit('user-command', $event)">
          <button class="icon-btn" type="button" :aria-label="`账号：${user.username}`">
            <span class="avatar" :style="{ width: '26px', height: '26px', fontSize: '11px', boxShadow: 'none', ...avatarColor(user.username) }">{{ user.username.slice(0, 1) }}</span>
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="mine">我的需求</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <button v-else class="icon-btn" type="button" aria-label="登录" @click="$emit('login')"><el-icon :size="18"><User /></el-icon></button>
      </div>
    </div>

    <nav class="mtabbar" aria-label="主导航">
      <button v-for="tab in primaryTabs.slice(0, 2)" :key="tab.key" type="button" class="mtab"
        :class="{ active: active === tab.key }" :aria-current="active === tab.key ? 'page' : undefined" @click="go(tab.key)">
        <span class="mtab-ico"><el-icon :size="20"><component :is="tab.icon" /></el-icon></span>
        <span>{{ tab.short }}</span>
      </button>
      <button class="mtab-fab" type="button" aria-label="提交需求" @click="go('submit')">
        <el-icon :size="22"><Plus /></el-icon>
      </button>
      <button v-for="tab in primaryTabs.slice(2)" :key="tab.key" type="button" class="mtab"
        :class="{ active: active === tab.key }" :aria-current="active === tab.key ? 'page' : undefined" @click="go(tab.key)">
        <span class="mtab-ico"><el-icon :size="20"><component :is="tab.icon" /></el-icon></span>
        <span>{{ tab.short }}</span>
      </button>
      <button type="button" class="mtab" :class="{ active: sheetOpen }" :aria-expanded="sheetOpen"
        aria-controls="rp-mobile-sheet" @click="sheetOpen = !sheetOpen">
        <span class="mtab-ico"><el-icon :size="20"><Grid v-if="!sheetOpen" /><Close v-else /></el-icon></span>
        <span>{{ sheetOpen ? '收起' : '更多' }}</span>
      </button>
    </nav>

    <Transition name="sheet">
      <div v-if="sheetOpen" class="msheet-mask" @click="sheetOpen = false"></div>
    </Transition>
    <Transition name="sheet">
      <div v-if="sheetOpen" id="rp-mobile-sheet" class="msheet" role="dialog" aria-label="全部页面">
        <div class="msheet-handle"></div>
        <div class="msheet-title"><strong>全部页面</strong><small>{{ items.length }} 个入口</small></div>
        <div v-for="group in groups" :key="group.label" class="msheet-group">
          <p class="msheet-group-label">{{ group.label }}</p>
          <div class="msheet-grid">
            <button v-for="item in group.items" :key="item.key" type="button" class="msheet-item"
              :class="{ active: active === item.key }" @click="go(item.key)">
              <span class="ico"><el-icon :size="17"><component :is="item.icon" /></el-icon></span>
              <span>{{ item.label }}</span>
            </button>
          </div>
        </div>
        <div class="rail-tools" style="border-top:1px solid var(--line);padding-top:12px">
          <button class="rail-tool" type="button" @click="toggleTheme">
            <el-icon :size="16"><Sunny v-if="isDark" /><Moon v-else /></el-icon>
            <span>{{ isDark ? '切换到浅色' : '切换到深色' }}</span>
          </button>
          <button v-if="!user" class="rail-tool" type="button" style="color:var(--primary)" @click="sheetOpen = false; $emit('login')">
            <el-icon :size="16"><User /></el-icon><span>登录 / 注册</span>
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, type Component } from 'vue'
import { ArrowUp, Bell, Close, Expand, Fold, Grid, Moon, Plus, Search, Sunny, User } from '@element-plus/icons-vue'
import logoUrl from '../assets/logo.svg'
import { avatarColor, roleLabel } from '../labels'
import type { User as ApiUser } from '../api'
import type { AppTab } from '../router'

const props = defineProps<{
  items: Array<{ key: AppTab; label: string; icon: Component }>
  active: AppTab
  collapsed: boolean
  user: ApiUser | null
  badges?: Record<string, number | string>
}>()
const emit = defineEmits<{
  navigate: [tab: AppTab]
  notification: []
  login: []
  toggle: []
  command: []
  'user-command': [command: string | number | object]
}>()

const navElement = ref<HTMLElement | null>(null)
const sheetOpen = ref(false)
const shortcut = navigator.platform.startsWith('Mac') ? '⌘K' : 'Ctrl K'

/* ---- 页面分组：让导航有信息架构，而不是一长串平铺 ---- */
const groupOf: Record<string, string> = {
  assistant: '共创', public: '共创', submit: '共创', mine: '共创',
  versions: '规划', dashboard: '规划', usage: '规划',
  admin: '管理', notifications: '管理', 'ai-settings': '管理', 'ai-usage': '管理', integrations: '管理', users: '管理',
}
const order = ['共创', '规划', '管理']
const groups = computed(() => order
  .map(label => ({ label, items: props.items.filter(item => (groupOf[item.key] ?? '规划') === label) }))
  .filter(group => group.items.length))

const shortLabels: Record<string, string> = {
  'AI 助手': 'AI', '公开需求': '需求', '提交需求': '提交',
  '我的需求与本机记录': '我的', '本机提交记录': '我的', '版本计划': '版本',
  'Token 用量': '用量', '总览看板': '总览', '需求审核': '审核',
  'AI 设置': 'AI 设置', '集成设置': '集成', '角色管理': '角色', '邮件通知': '邮件',
}
const primaryKeys: AppTab[] = ['assistant', 'public', 'mine']
const primaryTabs = computed(() => primaryKeys
  .map(key => props.items.find(item => item.key === key))
  .filter((item): item is NonNullable<typeof item> => !!item)
  .map(item => ({ ...item, short: shortLabels[item.label] ?? item.label })))

/* ---- 主题 ---- */
const isDark = ref(false)
function applyTheme(dark: boolean) {
  isDark.value = dark
  const root = document.documentElement
  root.dataset.theme = dark ? 'dark' : 'light'
  root.classList.toggle('dark', dark)
  try { localStorage.setItem('rp_theme', dark ? 'dark' : 'light') } catch { /* 主题偏好可选 */ }
}
function toggleTheme() { applyTheme(!isDark.value) }

function go(key: AppTab) {
  sheetOpen.value = false
  emit('navigate', key)
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') sheetOpen.value = false
}
onMounted(() => {
  let stored: string | null = null
  try { stored = localStorage.getItem('rp_theme') } catch { /* 忽略 */ }
  applyTheme(stored ? stored === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches)
  window.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
watch(() => props.active, () => { sheetOpen.value = false })

function scrollActiveIntoView() {
  navElement.value?.querySelector<HTMLElement>('button.active')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}
defineExpose({ scrollActiveIntoView })
</script>

<style scoped>
.sheet-enter-active, .sheet-leave-active { transition: opacity .24s var(--ease); }
.sheet-enter-from, .sheet-leave-to { opacity: 0; }
.msheet.sheet-enter-active, .msheet.sheet-leave-active { transition: transform .3s var(--ease), opacity .24s var(--ease); }
.msheet.sheet-enter-from, .msheet.sheet-leave-to { transform: translateY(100%); opacity: 1; }
</style>