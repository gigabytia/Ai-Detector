<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { EventRead } from '@/api/events'
import { eventGeometry } from '@/lib/eventGeometry'
import { Button } from '@/components/ui/button'
const props = defineProps<{ event: EventRead }>()
const { t } = useI18n()
const failed = ref(false)
const loaded = ref(false)
const overlay = ref(true)
const attempt = ref(0)
const geometry = computed(() => eventGeometry(props.event.metadata))
watch(
  () => [props.event.id, props.event.snapshot_url],
  () => {
    failed.value = false
    loaded.value = false
    attempt.value = 0
  },
)
function retry() {
  failed.value = false
  loaded.value = false
  attempt.value++
}
</script>

<template>
  <section class="bg-card min-w-0 space-y-3 rounded-lg border p-4" aria-labelledby="snapshot-title">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h2 id="snapshot-title" class="font-semibold">{{ t('snapshots.title') }}</h2>
      <label v-if="event.snapshot_url" class="flex items-center gap-2 text-xs"
        ><input v-model="overlay" type="checkbox" />{{ t('snapshots.overlay') }}</label
      >
    </div>
    <div
      v-if="event.snapshot_url && !failed"
      class="relative w-full overflow-hidden rounded-md bg-black"
      :style="{ aspectRatio: `${event.snapshot_width ?? 16} / ${event.snapshot_height ?? 9}` }"
    >
      <img
        :key="`${event.snapshot_url}-${attempt}`"
        :src="event.snapshot_url + (attempt ? `?retry=${attempt}` : '')"
        :alt="t('snapshots.alt')"
        class="block h-full w-full object-contain"
        @load="loaded = true"
        @error="failed = true"
      />
      <svg
        v-if="overlay && loaded"
        viewBox="0 0 1000 1000"
        preserveAspectRatio="none"
        class="pointer-events-none absolute inset-0 h-full w-full"
        aria-hidden="true"
        data-snapshot-overlay
      >
        <rect
          v-if="geometry.bbox"
          v-bind="geometry.bbox"
          fill="none"
          stroke="#ff5252"
          stroke-width="2"
          vector-effect="non-scaling-stroke"
        />
        <circle
          v-if="geometry.anchor"
          :cx="geometry.anchor.x"
          :cy="geometry.anchor.y"
          r="5"
          fill="#ffdf45"
        />
      </svg>
      <p
        v-if="!loaded"
        class="absolute inset-0 flex items-center justify-center text-sm text-white"
        role="status"
      >
        {{ t('detection.loading') }}
      </p>
    </div>
    <div
      v-else
      class="text-muted-foreground rounded-md border border-dashed p-8 text-center text-sm"
      role="status"
    >
      <p>{{ t(failed ? 'snapshots.missing' : 'snapshots.unavailable') }}</p>
      <Button v-if="failed" class="mt-3" size="sm" variant="outline" @click="retry">{{
        t('events.retry')
      }}</Button>
    </div>
    <p class="text-muted-foreground text-xs">{{ t('snapshots.hint') }}</p>
  </section>
</template>
