<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useSystemStatus } from '@/composables/useSystemStatus'

const { t } = useI18n()
const { level } = useSystemStatus()

// Colour is never the only signal: the label is always shown (ТЗ §118).
const dotClass = computed(
  () =>
    ({
      ok: 'bg-normal',
      degraded: 'bg-warning',
      down: 'bg-critical',
      loading: 'bg-neutral',
    })[level.value],
)
</script>

<template>
  <RouterLink
    to="/settings"
    class="hover:bg-accent focus-visible:ring-ring flex items-center gap-2 rounded-md px-2 py-1 text-xs focus-visible:ring-2 focus-visible:outline-none"
    role="status"
  >
    <span class="size-2 rounded-full" :class="dotClass" aria-hidden="true" />
    {{ t(`system.summary.${level}`) }}
  </RouterLink>
</template>
