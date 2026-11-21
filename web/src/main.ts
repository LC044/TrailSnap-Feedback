import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus, { ID_INJECTION_KEY } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import App from './App.vue'
import { router } from './router'
import './style.css'

/* 在首帧前恢复主题，避免浅色闪一下。 */
try {
  const stored = localStorage.getItem('rp_theme')
  const dark = stored ? stored === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
  document.documentElement.classList.toggle('dark', dark)
} catch { /* 读不到偏好时保持浅色。 */ }

createApp(App)
  .use(createPinia())
  .use(router)
  .use(ElementPlus, { locale: zhCn })
  .provide(ID_INJECTION_KEY, { prefix: 1024, current: 0 })
  .mount('#app')