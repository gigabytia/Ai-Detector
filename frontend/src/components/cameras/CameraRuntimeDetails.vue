<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Camera } from '@/api/cameras'
import { useNow } from '@/composables/useNow'
import { cameraDisplayState, secondsSinceLastFrame } from '@/lib/cameraStatus'

const props = defineProps<{ camera: Camera }>()
const { t, locale } = useI18n()
const now = useNow()

const state = computed(() => cameraDisplayState(props.camera))
const runtime = computed(() => props.camera.runtime)
const frameAge = computed(() => secondsSinceLastFrame(props.camera, now.value))

function time(value: string | null | undefined): string {
  return value
    ? new Date(value).toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' })
    : '—'
}
</script>

<template>
  <!-- §120: explain what is happening instead of showing raw errors. -->
  <div v-if="state === 'reconnecting'" class="space-y-0.5 text-xs" role="status">
    <p class="text-critical text-sm font-medium">{{ t('cameras.details.unavailable') }}</p>
    <p class="text-muted-foreground">
      {{ t('cameras.details.lastAttempt', { time: time(runtime?.last_reconnect_attempt_at) }) }}
    </p>
    <p class="text-muted-foreground">{{ t('cameras.details.reconnecting') }}</p>
  </div>
  <div v-else-if="state === 'error'" class="space-y-0.5 text-xs" role="alert">
    <p class="text-critical text-sm font-medium">{{ t('cameras.details.failed') }}</p>
    <p class="text-muted-foreground">{{ t('cameras.details.failedHint') }}</p>
    <p v-if="runtime?.last_error" class="text-muted-foreground font-mono text-xs break-all">
      {{ runtime.last_error }}
    </p>
  </div>
  <p v-else-if="state === 'no_worker'" class="text-warning text-sm">
    {{ t('cameras.details.noWorker') }}
  </p>
  <dl
    v-else-if="runtime && state === 'live'"
    class="text-muted-foreground flex flex-wrap gap-x-4 gap-y-0.5 text-xs"
  >
    <div class="flex gap-1">
      <dt>{{ t('cameras.details.fps') }}</dt>
      <dd class="text-foreground tabular-nums">{{ runtime.capture_fps.toFixed(1) }}</dd>
    </div>
    <div v-if="runtime.frame_size" class="flex gap-1">
      <dt>{{ t('cameras.details.resolution') }}</dt>
      <dd class="text-foreground tabular-nums">
        {{ runtime.frame_size[0] }}×{{ runtime.frame_size[1] }}
      </dd>
    </div>
    <div v-if="frameAge !== null" class="flex gap-1">
      <dt>{{ t('cameras.details.lastFrame') }}</dt>
      <dd class="text-foreground tabular-nums">
        {{ t('cameras.details.secondsAgo', { n: frameAge }) }}
      </dd>
    </div>
  </dl>
</template>
