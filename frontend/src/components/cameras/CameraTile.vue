<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { Camera } from '@/api/cameras'
import CameraLiveView from './CameraLiveView.vue'

import CameraRuntimeDetails from './CameraRuntimeDetails.vue'
import CameraStatusBadge from './CameraStatusBadge.vue'

defineProps<{ camera: Camera }>()
const { t } = useI18n()
</script>

<template>
  <article class="bg-card overflow-hidden rounded-lg border" :aria-label="camera.name">
    <RouterLink
      :to="`/monitoring/${camera.id}`"
      class="block"
      :aria-label="t('live.open', { name: camera.name })"
      ><CameraLiveView :camera="camera"
    /></RouterLink>
    <div class="space-y-2 p-3">
      <div class="flex items-center justify-between gap-2">
        <h2 class="truncate text-sm font-semibold">{{ camera.name }}</h2>
        <CameraStatusBadge :camera="camera" />
      </div>
      <CameraRuntimeDetails :camera="camera" />
    </div>
  </article>
</template>
