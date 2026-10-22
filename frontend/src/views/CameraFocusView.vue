<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import type { Point } from '@/api/zones'
import ZoneEditor from '@/components/cameras/ZoneEditor.vue'
import CameraTelemetry from '@/components/cameras/CameraTelemetry.vue'
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
const editing = ref(false)
const points = ref<Point[]>([])
watch(
  () => route.params.cameraId,
  () => {
    editing.value = false
    points.value = []
  },
)
function addPoint(point: Point) {
  if (points.value.length < 64) points.value = [...points.value, point]
}
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
      <CameraLiveView
        :key="camera.id"
        :camera="camera"
        :editing="editing"
        :draft="points"
        @point="addPoint"
      />
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
    <aside class="space-y-5">
      <CameraTelemetry :camera-id="camera.id" :enabled="camera.enabled" />
      <ZoneEditor
        :key="camera.id"
        v-model:editing="editing"
        v-model:points="points"
        :camera-id="camera.id"
      />
      <CameraConfigPanel :key="camera.id" :camera-id="camera.id" />
    </aside>
  </div>
</template>
