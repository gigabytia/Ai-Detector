<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { useInfiniteQuery } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'
import { ApiError } from '@/api/http'
import { eventLabel } from '@/lib/eventLabel'
import { fetchEvents, exportEvents } from '@/api/events'
import EventCard from '@/components/events/EventCard.vue'
import PageHeader from '@/components/layout/PageHeader.vue'
import { Button } from '@/components/ui/button'
import { useCameras } from '@/composables/useCameras'
import { useRealtimeStore } from '@/stores/realtime'

const { t } = useI18n()
const realtime = useRealtimeStore()
const cameraId = ref('')
const status = ref('')
const eventType = ref('')
const hours = ref(0)
const until = ref(new Date().toISOString())
watch(hours, () => {
  until.value = new Date().toISOString()
})
const extra = computed(() => ({
  eventType: eventType.value,
  ...(hours.value
    ? {
        start: new Date(Date.parse(until.value) - hours.value * 3600000).toISOString(),
        end: until.value,
      }
    : {}),
}))
const filters = computed(() => ({ ...extra.value, cameraId: cameraId.value, status: status.value }))
const eventTypes = [
  'PERSON_ENTERED_DANGER_ZONE',
  'PERSON_CROSSED_LINE',
  'PERSON_LOITERING_IN_DANGER_ZONE',
]
const exporting = ref(false),
  exportError = ref('')
let controller: AbortController | undefined
onBeforeUnmount(() => controller?.abort())
async function download() {
  exporting.value = true
  exportError.value = ''
  controller = new AbortController()
  try {
    await exportEvents({ ...filters.value }, controller.signal)
  } catch (error) {
    if (!(error instanceof DOMException && error.name === 'AbortError')) {
      exportError.value =
        error instanceof ApiError && error.code === 'EXPORT_TOO_LARGE'
          ? 'events.exportTooLarge'
          : 'events.exportError'
    }
  } finally {
    exporting.value = false
  }
}
const { data: cameras } = useCameras()
const query = useInfiniteQuery({
  queryKey: ['events', cameraId, status, extra],
  initialPageParam: undefined as string | undefined,
  queryFn: ({ pageParam, signal }) =>
    fetchEvents(pageParam, cameraId.value, status.value, signal, extra.value),
  getNextPageParam: (page) => page.next_cursor ?? undefined,
})
const persisted = computed(() => query.data.value?.pages.flatMap((p) => p.items) ?? [])
watch(persisted, (items) => realtime.persisted(new Set(items.map((e) => e.id))))
const events = computed(() => {
  const saved = new Map(persisted.value.map((e) => [e.id, e]))
  const live = realtime.alarms.filter(
    (e) =>
      !saved.has(e.id) &&
      (!cameraId.value || e.camera_id === cameraId.value) &&
      (!status.value || status.value === 'NEW') &&
      (!eventType.value || e.type === eventType.value) &&
      (!extra.value.start || Date.parse(e.occurred_at) >= Date.parse(extra.value.start)) &&
      (!extra.value.end || Date.parse(e.occurred_at) < Date.parse(extra.value.end)),
  )
  return [...live, ...saved.values()].sort((a, b) => b.occurred_at.localeCompare(a.occurred_at))
})
function cameraName(id: string) {
  return cameras.value?.find((c) => c.id === id)?.name ?? t('events.archivedCamera')
}
</script>

<template>
  <PageHeader :title="t('nav.events')">
    <template #actions>
      <div class="flex min-w-0 flex-wrap items-center justify-end gap-2">
        <span class="text-muted-foreground text-xs" role="status">{{
          t(realtime.connected ? 'events.live' : 'events.reconnecting')
        }}</span>
        <Button variant="outline" :disabled="exporting" @click="download">{{
          t(exporting ? 'events.exporting' : 'events.export')
        }}</Button>
      </div>
    </template>
  </PageHeader>
  <div class="mb-4 flex flex-wrap gap-3">
    <label class="space-y-1 text-xs"
      ><span class="block">{{ t('events.camera') }}</span
      ><select v-model="cameraId" class="bg-background max-w-full rounded-md border p-2 text-sm">
        <option value="">{{ t('events.allCameras') }}</option>
        <option v-for="c in cameras" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select></label
    >
    <label class="space-y-1 text-xs"
      ><span class="block">{{ t('events.filterStatus') }}</span
      ><select v-model="status" class="bg-background rounded-md border p-2 text-sm">
        <option value="">{{ t('events.allStatuses') }}</option>
        <option v-for="s in ['NEW', 'ACKNOWLEDGED', 'FALSE_POSITIVE']" :key="s" :value="s">
          {{ t(`events.status.${s}`) }}
        </option>
      </select></label
    >
    <label class="space-y-1 text-xs"
      ><span class="block">{{ t('events.filterType') }}</span>
      <select v-model="eventType" class="bg-background max-w-full rounded-md border p-2 text-sm">
        <option value="">{{ t('events.allTypes') }}</option>
        <option v-for="kind in eventTypes" :key="kind" :value="kind">
          {{ t(eventLabel(kind)) }}
        </option>
      </select>
    </label>
    <label class="space-y-1 text-xs"
      ><span class="block">{{ t('analytics.period') }}</span>
      <select v-model="hours" class="bg-background rounded-md border p-2 text-sm">
        <option :value="0">{{ t('events.allTime') }}</option>
        <option :value="1">{{ t('analytics.hour') }}</option>
        <option :value="24">{{ t('analytics.day') }}</option>
        <option :value="168">{{ t('analytics.week') }}</option>
      </select>
    </label>
    <Button
      v-if="hours"
      variant="outline"
      class="self-end"
      @click="until = new Date().toISOString()"
      >{{ t('analytics.refresh') }}</Button
    >
  </div>
  <p v-if="hours" class="text-muted-foreground mb-3 text-xs">
    {{ t('analytics.window') }}: {{ new Date(extra.start!).toLocaleString('ru-RU') }} —
    {{ new Date(extra.end!).toLocaleString('ru-RU') }}
  </p>
  <p class="text-muted-foreground mb-3 text-xs">{{ t('events.exportHint') }}</p>
  <p v-if="exportError" role="alert" class="text-critical mb-3 text-sm">{{ t(exportError) }}</p>
  <p v-if="query.isError.value" role="alert" class="text-critical mb-4 text-sm">
    {{ t('events.loadError') }}
    <Button size="sm" variant="outline" @click="query.refetch()">{{ t('events.retry') }}</Button>
  </p>
  <p v-if="query.isPending.value && !events.length" class="text-muted-foreground text-sm">
    {{ t('detection.loading') }}
  </p>
  <p
    v-else-if="!events.length"
    class="text-muted-foreground rounded-lg border p-8 text-center text-sm"
  >
    {{ t('events.empty') }}
  </p>
  <div class="grid min-w-0 gap-3 lg:grid-cols-2">
    <EventCard
      v-for="event in events"
      :key="event.id"
      :event="event"
      :camera-name="cameraName(event.camera_id)"
    />
  </div>
  <Button
    v-if="query.hasNextPage.value"
    variant="outline"
    class="mt-4"
    :disabled="query.isFetchingNextPage.value"
    @click="query.fetchNextPage()"
    >{{ t('events.more') }}</Button
  >
</template>
