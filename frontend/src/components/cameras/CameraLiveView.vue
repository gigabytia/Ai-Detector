<script setup lang="ts">
import { useElementVisibility } from '@vueuse/core'
import { computed, onBeforeUnmount, onMounted, ref, toRef } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Point } from '@/api/zones'
import { imagePoint } from '@/lib/live/geometry'
import type { Camera } from '@/api/cameras'
import { useCameraLive } from '@/composables/useCameraLive'
import { useNow } from '@/composables/useNow'
import { overlayPeople } from '@/lib/live/overlay'

const props = defineProps<{ camera: Camera; editing?: boolean; draft?: Point[] }>()
const emit = defineEmits<{ point: [point: Point] }>()
const { t } = useI18n()
const root = ref<HTMLElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
const visible = useElementVisibility(root)
const active = computed(
  () =>
    visible.value &&
    props.camera.enabled &&
    ['RUNNING', 'DEGRADED'].includes(props.camera.runtime?.status ?? ''),
)
const id = toRef(() => props.camera.id)
const { frame, state, receivedAt } = useCameraLive(id, active)
const now = useNow()
const stale = computed(() => receivedAt.value > 0 && now.value - receivedAt.value > 3000)
const message = computed(() => {
  if (!props.camera.enabled) return t('live.stopped')
  if (props.camera.runtime?.status === 'ERROR') return t('cameras.details.failed')
  if (stale.value) return t('live.stale')
  if (!active.value) return t('live.connecting')
  return t(`live.${state.value}`)
})

const dangerCount = computed(
  () => frame.value?.metadata.tracks?.filter((t) => t.state === 'IN_DANGER_ZONE').length ?? 0,
)
const svgPoints = (points: Point[]) =>
  points
    .map(
      (p) => `${p.x * (frame.value?.image.width ?? 1)},${p.y * (frame.value?.image.height ?? 1)}`,
    )
    .join(' ')
function addPoint(event: MouseEvent) {
  if (!props.editing || !frame.value || stale.value || state.value !== 'live' || !root.value) return
  const rect = root.value.getBoundingClientRect()
  const p = imagePoint(
    event.clientX - rect.left,
    event.clientY - rect.top,
    rect.width,
    rect.height,
    frame.value.image.width,
    frame.value.image.height,
  )
  if (p) emit('point', p)
}
let raf = 0
let drawn: typeof frame.value = null
function draw() {
  const value = frame.value
  const target = canvas.value
  if (!value && drawn && target) {
    target.getContext('2d')?.clearRect(0, 0, target.width, target.height)
    drawn = null
  }
  if (value && target && value !== drawn) {
    const ctx = target.getContext('2d')
    if (ctx) {
      target.width = value.image.width
      target.height = value.image.height
      ctx.drawImage(value.image, 0, 0)
      const scale = Math.max(1, target.width / 640)
      ctx.strokeStyle = '#6ee7b7'
      ctx.fillStyle = '#6ee7b7'
      ctx.lineWidth = 2 * scale
      ctx.font = `${12 * scale}px Arial`
      for (const d of overlayPeople(value.metadata)) {
        const [x1, y1, x2, y2] = d.bbox
        ctx.strokeStyle = d.inDanger ? '#fb7185' : '#6ee7b7'
        ctx.strokeRect(
          x1 * target.width,
          y1 * target.height,
          (x2 - x1) * target.width,
          (y2 - y1) * target.height,
        )
        const identity = d.trackId === undefined ? '' : ` #${d.trackId}`
        const label = `${t('live.person')}${identity} ${Math.round(d.confidence * 100)}%`
        const x = x1 * target.width
        const y = Math.max(16 * scale, y1 * target.height)
        const width = ctx.measureText(label).width + 8 * scale
        ctx.fillStyle = d.inDanger ? '#4c0519' : '#052e24'
        ctx.fillRect(x, y - 16 * scale, width, 16 * scale)
        ctx.fillStyle = d.inDanger ? '#fda4af' : '#6ee7b7'
        ctx.fillText(label, x + 4 * scale, y - 4 * scale)
      }
      drawn = value
    }
  }
  raf = requestAnimationFrame(draw)
}
onMounted(() => {
  raf = requestAnimationFrame(draw)
})
onBeforeUnmount(() => cancelAnimationFrame(raf))
</script>

<template>
  <div ref="root" class="relative aspect-video w-full overflow-hidden bg-stone-950 text-stone-300">
    <canvas
      ref="canvas"
      class="h-full w-full object-contain"
      :class="{ 'opacity-35': stale }"
      :aria-label="t('live.label', { name: camera.name })"
    />
    <svg
      v-if="frame"
      :viewBox="`0 0 ${frame.image.width} ${frame.image.height}`"
      preserveAspectRatio="xMidYMid meet"
      class="absolute inset-0 h-full w-full"
      :class="editing ? 'cursor-crosshair' : 'pointer-events-none'"
      :aria-label="t('zones.canvas')"
      @click="addPoint"
    >
      <template v-if="!editing">
        <polygon
          v-for="zone in frame.metadata.zones ?? []"
          :key="zone.id"
          :points="svgPoints(zone.points)"
          fill="#fb7185"
          fill-opacity="0.15"
          stroke="#fb7185"
          stroke-width="2"
          vector-effect="non-scaling-stroke"
        >
          <title>{{ zone.name }}</title>
        </polygon>
      </template>
      <template v-else>
        <polygon
          v-if="(draft?.length ?? 0) >= 3"
          :points="svgPoints(draft ?? [])"
          fill="#fbbf24"
          fill-opacity="0.15"
        />
        <polyline
          :points="svgPoints(draft ?? [])"
          fill="none"
          stroke="#fbbf24"
          stroke-width="2"
          vector-effect="non-scaling-stroke"
        />
        <circle
          v-for="(p, i) in draft ?? []"
          :key="i"
          :cx="p.x * frame.image.width"
          :cy="p.y * frame.image.height"
          :r="frame.image.width / 150"
          fill="#fbbf24"
        />
      </template>
    </svg>
    <div
      v-if="!frame || stale || state !== 'live'"
      class="absolute inset-0 flex items-center justify-center bg-black/30 px-5 text-center text-sm"
      role="status"
    >
      {{ message }}
    </div>
    <div
      v-if="frame && !stale"
      class="absolute bottom-2 left-2 rounded bg-black/70 px-2 py-1 text-xs tabular-nums"
    >
      {{ t('live.people', { n: frame.metadata.detections.length }) }}
      <span v-if="dangerCount" class="ml-2 text-rose-300">{{
        t('zones.dangerCount', { n: dangerCount })
      }}</span>
    </div>
    <span
      v-if="camera.source_type === 'mock'"
      class="absolute top-2 left-2 rounded bg-black/70 px-2 py-1 text-[10px] font-semibold tracking-wider"
      >{{ t('live.demo') }}</span
    >
  </div>
</template>
