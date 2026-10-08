<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useSystemStatus } from '@/composables/useSystemStatus'

const { t, te, locale } = useI18n()
const { data, isError, isPending } = useSystemStatus()

const checkedAt = computed(() =>
  data.value ? new Date(data.value.checked_at).toLocaleTimeString(locale.value) : '',
)

function dependencyLabel(name: string): string {
  const key = `system.dependency.${name}`
  return te(key) ? t(key) : name
}
</script>

<template>
  <section class="bg-card max-w-2xl rounded-lg border p-4" aria-labelledby="system-status-title">
    <h2 id="system-status-title" class="mb-3 text-sm font-semibold">{{ t('system.title') }}</h2>

    <p v-if="isError" class="text-critical text-sm" role="alert">{{ t('system.loadError') }}</p>
    <div v-else-if="isPending" class="space-y-2" aria-busy="true">
      <div class="bg-muted h-4 w-1/2 animate-pulse rounded" />
      <div class="bg-muted h-4 w-1/3 animate-pulse rounded" />
    </div>

    <template v-else-if="data">
      <dl class="divide-y text-sm">
        <div v-for="item in data.dependencies" :key="item.name" class="flex justify-between py-2">
          <dt>{{ dependencyLabel(item.name) }}</dt>
          <dd :class="item.ok ? 'text-normal' : 'text-critical'">
            {{ item.ok ? t('system.ok') : t('system.unavailable') }}
          </dd>
        </div>
      </dl>

      <h3 class="mt-4 mb-2 text-sm font-semibold">{{ t('system.workers') }}</h3>
      <p v-if="data.workers.length === 0" class="text-warning text-sm">
        {{ t('system.noWorkers') }}
      </p>
      <ul v-else class="divide-y text-sm">
        <li
          v-for="worker in data.workers"
          :key="worker.worker_id"
          class="flex justify-between py-2"
        >
          <span class="font-mono text-xs">{{ worker.worker_id }}</span>
          <span class="text-muted-foreground">
            {{ t('system.uptime', { minutes: Math.floor(worker.uptime_seconds / 60) }) }}
          </span>
        </li>
      </ul>

      <p class="text-muted-foreground mt-4 text-xs">
        {{ t('system.checkedAt', { time: checkedAt }) }}
      </p>
    </template>
  </section>
</template>
