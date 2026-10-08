<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Camera } from '@/api/cameras'
import { cameraDisplayState, TONE, type Tone } from '@/lib/cameraStatus'

const props = defineProps<{ camera: Camera }>()
const { t } = useI18n()

const state = computed(() => cameraDisplayState(props.camera))

const TONE_CLASS: Record<Tone, string> = {
  normal: 'bg-normal/12 text-normal',
  warning: 'bg-warning/12 text-warning',
  critical: 'bg-critical/12 text-critical',
  neutral: 'bg-muted text-muted-foreground',
}
const DOT_CLASS: Record<Tone, string> = {
  normal: 'bg-normal',
  warning: 'bg-warning',
  critical: 'bg-critical',
  neutral: 'bg-neutral',
}
</script>

<template>
  <span
    class="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap"
    :class="TONE_CLASS[TONE[state]]"
    :data-state="state"
  >
    <span
      class="size-1.5 rounded-full"
      :class="[DOT_CLASS[TONE[state]], { 'animate-pulse': state === 'live' }]"
      aria-hidden="true"
    />
    {{ t(`cameras.state.${state}`) }}
  </span>
</template>
