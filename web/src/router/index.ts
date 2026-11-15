import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { APP_BASE_PATH } from '../runtimeBase'

export type AppTab = 'public' | 'dashboard' | 'submit' | 'mine' | 'admin' | 'versions' | 'usage' | 'integrations' | 'ai-settings' | 'users' | 'notifications'

// App.vue still owns the shell while pages are migrated one at a time. Route
// records are authoritative for URLs and browser history during that migration.
const RouteTarget = { render: () => null }
const tabRoutes: Array<[AppTab, string]> = [
  ['public', '/'],
  ['dashboard', '/dashboard'],
  ['submit', '/requirements/new'],
  ['mine', '/requirements/mine'],
  ['admin', '/admin/requirements'],
  ['versions', '/versions'],
  ['usage', '/usage'],
  ['integrations', '/settings/integrations'],
  ['ai-settings', '/settings/ai'],
  ['users', '/settings/users'],
  ['notifications', '/settings/notifications'],
]

const routes: RouteRecordRaw[] = [
  { path: '/requirements/REQ-:number(\\d+)/conversation', name: 'requirement-conversation', component: RouteTarget, meta: { tab: 'public' } },
  { path: '/notifications/:action(verify|unsubscribe)', name: 'notification-confirm', component: RouteTarget, meta: { tab: 'public' } },
  ...tabRoutes.map(([name, path]) => ({ path, name, component: RouteTarget, meta: { tab: name } })),
  { path: '/requirements/REQ-:number(\\d+)', name: 'requirement-detail', component: RouteTarget, meta: { tab: 'public' } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({
  history: createWebHistory(APP_BASE_PATH), routes,
  scrollBehavior: (_to, _from, saved) => saved || { top: 0 },
})
