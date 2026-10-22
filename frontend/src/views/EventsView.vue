<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useInfiniteQuery } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'
import { fetchEvents } from '@/api/events'
import EventCard from '@/components/events/EventCard.vue'
import PageHeader from '@/components/layout/PageHeader.vue'
import { Button } from '@/components/ui/button'
import { useCameras } from '@/composables/useCameras'
import { useRealtimeStore } from '@/stores/realtime'

const { t } = useI18n()
const realtime = useRealtimeStore()
const cameraId = ref('')
const status = ref('')
const { data: cameras } = useCameras()
const query = useInfiniteQuery({
  queryKey: ['events', cameraId, status],
  initialPageParam: undefined as string | undefined,
  queryFn: ({ pageParam, signal }) => fetchEvents(pageParam, cameraId.value, status.value, signal),
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
      (!status.value || status.value === 'NEW'),
  )
  return [...live, ...saved.values()].sort((a, b) => b.occurred_at.localeCompare(a.occurred_at))
})
function cameraName(id: string) {
  return cameras.value?.find((c) => c.id === id)?.name ?? t('events.archivedCamera')
}
</script>

<template>
  <PageHeader :title="t('nav.events')">
    <template #actions
      ><span class="text-muted-foreground text-xs" role="status">{{
        t(realtime.connected ? 'events.live' : 'events.reconnecting')
      }}</span></template
    >
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
  </div>
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
