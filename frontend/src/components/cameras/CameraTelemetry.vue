<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTelemetry } from '@/composables/useTelemetry'
import { useNow } from '@/composables/useNow'
const props = defineProps<{ cameraId: string; enabled: boolean }>()
const { t } = useI18n()
const { data, receivedAt } = useTelemetry(
  computed(() => (props.enabled ? props.cameraId : undefined)),
)
const now = useNow()
const stale = computed(() => !receivedAt.value || now.value - receivedAt.value > 3000)
</script>
<template>
  <section class="bg-card space-y-2 rounded-lg border p-4" aria-live="polite">
    <h2 class="text-sm font-semibold">{{ t('events.telemetry') }}</h2>
    <p v-if="stale" class="text-muted-foreground text-xs">
      {{ t(data ? 'events.telemetryStale' : 'events.telemetryWaiting') }}
    </p>
    <div v-else-if="data" class="flex flex-wrap gap-3 text-xs">
      <span>{{ t('events.people', { n: data.persons }) }}</span
      ><span>{{ t('events.inZone', { n: data.persons_in_zone }) }}</span
      ><span>{{ t('events.inference', { n: Math.round(data.inference_ms) }) }}</span>
    </div>
  </section>
</template>
