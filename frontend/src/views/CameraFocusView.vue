<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import CameraConfigPanel from '@/components/cameras/CameraConfigPanel.vue'
import CameraLiveView from '@/components/cameras/CameraLiveView.vue'
import CameraRuntimeDetails from '@/components/cameras/CameraRuntimeDetails.vue'
import CameraStatusBadge from '@/components/cameras/CameraStatusBadge.vue'
import PageHeader from '@/components/layout/PageHeader.vue'
import { Button } from '@/components/ui/button'
import { useCameraMutations, useCameras } from '@/composables/useCameras'

const { t } = useI18n()
const route = useRoute()
const { data: cameras, isPending, isError } = useCameras()
const camera = computed(() => cameras.value?.find((c) => c.id === route.params.cameraId))
const { action } = useCameraMutations()
</script>

<template>
  <PageHeader :title="camera?.name ?? t('nav.monitoring')">
    <template #actions
      ><Button variant="outline" size="sm" as-child
        ><RouterLink to="/monitoring">{{ t('live.back') }}</RouterLink></Button
      ></template
    >
  </PageHeader>
  <p v-if="isPending" class="text-muted-foreground text-sm">{{ t('detection.loading') }}</p>
  <p v-else-if="isError && !cameras" class="text-critical text-sm" role="alert">
    {{ t('cameras.loadError') }}
  </p>
  <p v-else-if="!camera" class="text-muted-foreground text-sm">{{ t('live.notFound') }}</p>
  <div v-else class="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
    <section class="bg-card overflow-hidden rounded-lg border">
      <CameraLiveView :key="camera.id" :camera="camera" />
      <div class="space-y-4 p-4">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <CameraStatusBadge :camera="camera" />
          <div class="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              :disabled="action.isPending.value"
              @click="action.mutate({ id: camera.id, action: camera.enabled ? 'stop' : 'start' })"
              >{{ t(camera.enabled ? 'cameras.actions.stop' : 'cameras.actions.start') }}</Button
            >
          </div>
        </div>
        <CameraRuntimeDetails :camera="camera" />
      </div>
    </section>
    <CameraConfigPanel :key="camera.id" :camera-id="camera.id" />
  </div>
</template>
