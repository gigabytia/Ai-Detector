<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'
import { fetchEvent } from '@/api/events'
import { useCameras } from '@/composables/useCameras'
import { ApiError } from '@/api/http'
import EventCard from '@/components/events/EventCard.vue'
import EventSnapshot from '@/components/events/EventSnapshot.vue'
import PageHeader from '@/components/layout/PageHeader.vue'
import { Button } from '@/components/ui/button'
const route = useRoute()
const { t } = useI18n()
const id = computed(() => String(route.params.eventId))
const { data: cameras } = useCameras()
const query = useQuery({
  queryKey: ['events', 'detail', id],
  queryFn: ({ signal }) => fetchEvent(id.value, signal),
  retry: false,
  // Live alarms may precede PostgreSQL; retry without asking the user to navigate away.
  refetchInterval: 5000,
})
const event = query.data
const notFound = computed(
  () => query.error.value instanceof ApiError && query.error.value.status === 404,
)
const cameraName = computed(
  () =>
    cameras.value?.find((c) => c.id === event.value?.camera_id)?.name ?? t('events.archivedCamera'),
)
</script>

<template>
  <PageHeader :title="t('snapshots.details')"
    ><template #actions
      ><RouterLink to="/events" class="text-sm underline">{{
        t('snapshots.back')
      }}</RouterLink></template
    ></PageHeader
  >
  <p v-if="query.isPending.value" role="status" class="text-sm">{{ t('detection.loading') }}</p>
  <div v-if="query.isError.value" class="text-critical mb-4 space-y-3 text-sm" role="alert">
    <p>{{ t(notFound ? 'snapshots.notFound' : 'events.loadError') }}</p>
    <Button size="sm" variant="outline" @click="query.refetch()">{{ t('events.retry') }}</Button>
  </div>
  <div v-if="event" class="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
    <EventSnapshot :event="event" />
    <div class="min-w-0 space-y-4">
      <EventCard :event="event" :camera-name="cameraName" detail />
      <div
        v-if="event.type === 'PERSON_CROSSED_LINE'"
        class="bg-card space-y-2 rounded-lg border p-4 text-sm"
      >
        <p class="font-semibold">{{ t('lines.crossed') }}</p>
        <p class="break-words">{{ event.metadata.line_name }}</p>
        <p>
          {{
            t(
              event.metadata.direction === 'LEFT_TO_RIGHT'
                ? 'lines.negativePositive'
                : 'lines.positiveNegative',
            )
          }}
        </p>
        <p class="text-muted-foreground text-xs">{{ t('lines.directionHint') }}</p>
      </div>
      <div
        v-if="event.type === 'PERSON_LOITERING_IN_DANGER_ZONE'"
        class="bg-card space-y-2 rounded-lg border p-4 text-sm"
      >
        <p class="font-semibold">{{ t('events.loitering') }}</p>
        <p class="break-words">{{ event.metadata.zone_name }}</p>
        <p>
          {{
            t('events.loiteringDuration', {
              duration: Number(event.metadata.duration_seconds).toFixed(2),
              threshold: event.metadata.threshold_seconds,
            })
          }}
        </p>
      </div>
      <dl class="bg-card space-y-3 rounded-lg border p-4 text-xs">
        <div>
          <dt class="text-muted-foreground">{{ t('snapshots.eventId') }}</dt>
          <dd class="mt-1 font-mono break-all">{{ event.id }}</dd>
        </div>
        <div>
          <dt class="text-muted-foreground">{{ t('snapshots.runId') }}</dt>
          <dd class="mt-1 font-mono break-all">{{ event.run_id }}</dd>
        </div>
        <div>
          <dt class="text-muted-foreground">{{ t('snapshots.zoneId') }}</dt>
          <dd class="mt-1 font-mono break-all">{{ event.zone_id ?? '—' }}</dd>
        </div>
        <div>
          <dt class="text-muted-foreground">{{ t('snapshots.sourceTime') }}</dt>
          <dd class="mt-1">
            {{ (event.source_ts_ms / 1000).toFixed(2) }} {{ t('snapshots.seconds') }}
          </dd>
        </div>
        <div>
          <dt class="text-muted-foreground">{{ t('snapshots.detectorScore') }}</dt>
          <dd class="mt-1">{{ Math.round(event.detector_confidence * 100) }}%</dd>
        </div>
      </dl>
    </div>
  </div>
</template>
