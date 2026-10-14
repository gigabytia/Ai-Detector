<script setup lang="ts">
import { useElementVisibility } from '@vueuse/core'
import { computed, onBeforeUnmount, onMounted, ref, toRef } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Camera } from '@/api/cameras'
import { useCameraLive } from '@/composables/useCameraLive'
import { useNow } from '@/composables/useNow'

const props = defineProps<{ camera: Camera }>()
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
      for (const d of value.metadata.detections) {
        const [x1, y1, x2, y2] = d.bbox
        ctx.strokeRect(
          x1 * target.width,
          y1 * target.height,
          (x2 - x1) * target.width,
          (y2 - y1) * target.height,
        )
        const label = `${t('live.person')} ${Math.round(d.confidence * 100)}%`
        const x = x1 * target.width
        const y = Math.max(16 * scale, y1 * target.height)
        const width = ctx.measureText(label).width + 8 * scale
        ctx.fillStyle = '#052e24'
        ctx.fillRect(x, y - 16 * scale, width, 16 * scale)
        ctx.fillStyle = '#6ee7b7'
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
    </div>
    <span
      v-if="camera.source_type === 'mock'"
      class="absolute top-2 left-2 rounded bg-black/70 px-2 py-1 text-[10px] font-semibold tracking-wider"
      >{{ t('live.demo') }}</span
    >
  </div>
</template>
