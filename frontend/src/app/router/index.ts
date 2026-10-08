import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

export const navigationRoutes = [
  { path: '/monitoring', name: 'monitoring', titleKey: 'nav.monitoring' },
  { path: '/events', name: 'events', titleKey: 'nav.events' },
  { path: '/analytics', name: 'analytics', titleKey: 'nav.analytics' },
  { path: '/cameras', name: 'cameras', titleKey: 'nav.cameras' },
  { path: '/settings', name: 'settings', titleKey: 'nav.settings' },
] as const

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/monitoring' },
  {
    path: '/monitoring',
    name: 'monitoring',
    component: () => import('@/views/MonitoringView.vue'),
  },
  { path: '/events', name: 'events', component: () => import('@/views/EventsView.vue') },
  { path: '/analytics', name: 'analytics', component: () => import('@/views/AnalyticsView.vue') },
  { path: '/cameras', name: 'cameras', component: () => import('@/views/CamerasView.vue') },
  { path: '/settings', name: 'settings', component: () => import('@/views/SettingsView.vue') },
  { path: '/:pathMatch(.*)*', redirect: '/monitoring' },
]

export const router = createRouter({ history: createWebHistory(), routes })
