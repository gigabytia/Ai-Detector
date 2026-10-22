<script setup lang="ts">
import { eventLabel } from '@/lib/eventLabel'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import { updateEvent, type EventRead } from '@/api/events'
import type { LiveEvent } from '@/lib/live/events'
import { Button } from '@/components/ui/button'
import { ApiError } from '@/api/http'
import { useRealtimeStore } from '@/stores/realtime'

const props = defineProps<{ event: EventRead | LiveEvent; cameraName: string; detail?: boolean }>()
const { t } = useI18n()
const client = useQueryClient()
const realtime = useRealtimeStore()
const saved = computed(() => ('status' in props.event ? (props.event as EventRead) : null))
const status = computed(() => saved.value?.status ?? 'NEW')
const note = ref(saved.value?.note ?? '')
const dirty = ref(false)
const busy = ref(false)
watch(
  () => saved.value?.note,
  (value) => {
    if (!dirty.value) note.value = value ?? ''
  },
)
async function save(next?: 'ACKNOWLEDGED' | 'FALSE_POSITIVE') {
  busy.value = true
  try {
    await updateEvent(props.event.id, {
      ...(next ? { status: next } : {}),
      note: note.value || null,
    })
    realtime.persisted(new Set([props.event.id]))
    dirty.value = false
    await client.invalidateQueries({ queryKey: ['events'] })
  } catch (error) {
    toast.error(
      t(
        error instanceof ApiError && error.code === 'EVENT_NOT_PERSISTED_YET'
          ? 'events.retryLater'
          : 'events.saveError',
      ),
    )
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <article class="bg-card space-y-3 rounded-lg border p-4" :data-event-id="event.id">
    <div class="flex flex-wrap items-start justify-between gap-2">
      <div class="min-w-0">
        <p class="text-sm font-semibold">
          {{ t(eventLabel(event.type)) }}
        </p>
        <RouterLink
          :to="`/monitoring/${event.camera_id}`"
          class="text-muted-foreground text-sm break-words underline"
          >{{ cameraName }}</RouterLink
        >
      </div>
      <span
        class="rounded border px-2 py-1 text-xs"
        :class="status === 'NEW' ? 'text-critical' : 'text-muted-foreground'"
        >{{ t(`events.status.${status}`) }}</span
      >
    </div>
    <p class="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs">
      <time :datetime="event.occurred_at">{{
        new Date(event.occurred_at).toLocaleString('ru-RU')
      }}</time>
      <span>{{ t('events.track', { n: event.track_id }) }}</span>
      <span>{{ t(`events.severity.${event.severity}`) }}</span>
      <span>{{ t('events.confidence', { n: Math.round(event.event_confidence * 100) }) }}</span>
    </p>
    <p v-if="!saved" class="text-warning text-xs" role="status">{{ t('events.pending') }}</p>
    <label class="block space-y-1 text-xs">
      <span>{{ t('events.note') }}</span>
      <textarea
        v-model="note"
        maxlength="2000"
        rows="2"
        class="bg-background w-full rounded-md border p-2 text-sm"
        @input="dirty = true"
      />
    </label>
    <RouterLink v-if="!detail" :to="`/events/${event.id}`" class="inline-block text-sm underline">{{
      t('snapshots.details')
    }}</RouterLink>
    <div class="flex flex-wrap gap-2">
      <Button v-if="status === 'NEW'" size="sm" :disabled="busy" @click="save('ACKNOWLEDGED')">{{
        t('events.ack')
      }}</Button>
      <Button
        v-if="status === 'NEW'"
        size="sm"
        variant="outline"
        :disabled="busy"
        @click="save('FALSE_POSITIVE')"
        >{{ t('events.falsePositive') }}</Button
      >
      <Button size="sm" variant="outline" :disabled="busy || !dirty" @click="save()">{{
        t('events.saveNote')
      }}</Button>
    </div>
  </article>
</template>
