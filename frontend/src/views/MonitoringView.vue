<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import CamerasEmptyState from '@/components/cameras/CamerasEmptyState.vue'
import CameraTile from '@/components/cameras/CameraTile.vue'
import PageHeader from '@/components/layout/PageHeader.vue'
import { Button } from '@/components/ui/button'
import { useCameras } from '@/composables/useCameras'

const { t } = useI18n()
const { data: cameras, isPending, isError } = useCameras()
</script>

<template>
  <PageHeader :title="t('nav.monitoring')" />

  <p v-if="isError && !cameras" class="text-critical text-sm" role="alert">
    {{ t('cameras.loadError') }}
  </p>
  <div v-else-if="isPending" class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-busy="true">
    <div v-for="i in 3" :key="i" class="bg-muted aspect-video animate-pulse rounded-lg" />
  </div>
  <CamerasEmptyState v-else-if="cameras && cameras.length === 0">
    <Button class="mt-4" as-child>
      <RouterLink to="/cameras">{{ t('cameras.add') }}</RouterLink>
    </Button>
  </CamerasEmptyState>
  <div v-else class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
    <CameraTile v-for="camera in cameras" :key="camera.id" :camera="camera" />
  </div>
</template>
