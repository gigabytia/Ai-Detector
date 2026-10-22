<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { TrackSession } from '@/api/analytics'
const props = defineProps<{ track: TrackSession }>()
const { t } = useI18n()
const segments = computed(() => {
  const begin = Date.parse(props.track.started_at),
    duration = Math.max(1, Date.parse(props.track.ended_at) - begin)
  return props.track.segments.map((s) => ({
    ...s,
    left: (100 * (Date.parse(s.start) - begin)) / duration,
    width: (100 * (Date.parse(s.end) - Date.parse(s.start))) / duration,
  }))
})
const stamp = (value: string) => new Date(value).toLocaleString('ru-RU')
</script>
<template>
  <article class="min-w-0 space-y-2 rounded border p-3" data-track-timeline>
    <div class="flex flex-wrap justify-between gap-2 text-xs">
      <strong>{{ t('events.track', { n: track.track_id }) }}</strong
      ><span>{{ stamp(track.started_at) }} — {{ stamp(track.ended_at) }}</span>
    </div>
    <p class="text-muted-foreground truncate font-mono text-[11px]">
      {{ track.camera_id }} / {{ track.run_id }}
    </p>
    <div class="bg-muted relative h-5 overflow-hidden rounded" aria-hidden="true">
      <span
        v-for="(segment, i) in segments"
        :key="i"
        class="absolute top-0 h-full"
        :class="
          segment.state === 'IN_DANGER_ZONE'
            ? 'bg-red-500'
            : segment.state === 'LOST'
              ? 'bg-slate-400'
              : 'bg-emerald-500'
        "
        :style="{ left: `${segment.left}%`, width: `${segment.width}%` }"
      />
    </div>
    <details class="text-xs">
      <summary class="cursor-pointer">{{ t('analytics.segments') }}</summary>
      <ul class="mt-2 space-y-1">
        <li v-for="(segment, i) in segments" :key="i">
          {{ t(`analytics.states.${segment.state}`) }}: {{ stamp(segment.start) }} —
          {{ stamp(segment.end) }}
        </li>
      </ul>
    </details>
    <p v-if="track.truncated" class="text-warning text-xs">{{ t('analytics.truncated') }}</p>
  </article>
</template>
