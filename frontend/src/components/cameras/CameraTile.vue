<script setup lang="ts">
import { Video, VideoOff } from '@lucide/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Camera } from '@/api/cameras'
import { cameraDisplayState } from '@/lib/cameraStatus'

import CameraRuntimeDetails from './CameraRuntimeDetails.vue'
import CameraStatusBadge from './CameraStatusBadge.vue'

const props = defineProps<{ camera: Camera }>()
const { t } = useI18n()
const live = computed(() => cameraDisplayState(props.camera) === 'live')
</script>

<template>
  <article class="bg-card overflow-hidden rounded-lg border" :aria-label="camera.name">
    <!-- The video preview with person boxes is added in Milestone 4. -->
    <div
      class="flex aspect-video items-center justify-center bg-stone-900 text-stone-400"
      :class="{ 'text-stone-500': !live }"
    >
      <div class="flex flex-col items-center gap-2 text-xs">
        <component :is="live ? Video : VideoOff" class="size-6" aria-hidden="true" />
        <span>{{ live ? t('cameras.tile.streamActive') : t('cameras.tile.noStream') }}</span>
      </div>
    </div>
    <div class="space-y-2 p-3">
      <div class="flex items-center justify-between gap-2">
        <h2 class="truncate text-sm font-semibold">{{ camera.name }}</h2>
        <CameraStatusBadge :camera="camera" />
      </div>
      <CameraRuntimeDetails :camera="camera" />
    </div>
  </article>
</template>
