<script setup lang="ts">
import { BarChart3, Bell, Camera, MonitorPlay, Settings, type LucideIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { navigationRoutes } from '@/app/router'

const { t } = useI18n()

const icons: Record<(typeof navigationRoutes)[number]['name'], LucideIcon> = {
  monitoring: MonitorPlay,
  events: Bell,
  analytics: BarChart3,
  cameras: Camera,
  settings: Settings,
}
</script>

<template>
  <nav class="bg-card w-14 shrink-0 border-r md:w-52" :aria-label="t('app.title')">
    <ul class="flex flex-col gap-1 p-2">
      <li v-for="item in navigationRoutes" :key="item.name">
        <RouterLink
          :to="item.path"
          class="text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:ring-ring flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors duration-150 focus-visible:ring-2 focus-visible:outline-none"
          active-class="bg-accent text-foreground font-medium"
        >
          <component :is="icons[item.name]" class="size-4 shrink-0" aria-hidden="true" />
          <span class="hidden md:inline">{{ t(item.titleKey) }}</span>
        </RouterLink>
      </li>
    </ul>
  </nav>
</template>
