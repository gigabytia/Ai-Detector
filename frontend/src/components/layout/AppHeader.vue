<script setup lang="ts">
import { ScanEye } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import SystemStatusIndicator from './SystemStatusIndicator.vue'
import ThemeToggle from './ThemeToggle.vue'

const { t } = useI18n()
</script>

<template>
  <header class="bg-card flex h-12 items-center gap-3 border-b px-4">
    <ScanEye class="size-5" aria-hidden="true" />
    <span class="text-sm font-semibold tracking-tight">{{ t('app.title') }}</span>
    <div class="ml-auto flex items-center gap-2">
      <SystemStatusIndicator />
      <ThemeToggle />
    </div>
  </header>
</template>
