<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { fetchCameraConfig, saveCameraConfig, type CameraConfigOverrides } from '@/api/cameras'
import { Button } from '@/components/ui/button'
import { errorMessageKey } from '@/lib/apiErrors'

const props = defineProps<{ cameraId: string }>()
const { t } = useI18n()
const client = useQueryClient()
const key = computed(() => ['camera-config', props.cameraId])
const query = useQuery({
  queryKey: key,
  queryFn: ({ signal }) => fetchCameraConfig(props.cameraId, signal),
  refetchOnWindowFocus: false,
})
const fps = ref<string | number>('')
const confidence = ref<string | number>('')
const saved = ref(false)
const invalid = ref(false)
watch(
  query.data,
  (value) => {
    fps.value = value?.overrides.target_fps?.toString() ?? ''
    confidence.value = value?.overrides.detection_confidence?.toString() ?? ''
  },
  { immediate: true },
)
watch([fps, confidence], () => {
  saved.value = false
  invalid.value = false
})
const mutation = useMutation({
  mutationFn: ({ id, body }: { id: string; body: CameraConfigOverrides }) =>
    saveCameraConfig(id, body),
  onSuccess: async (value, { id }) => {
    client.setQueryData(['camera-config', id], value)
    await nextTick()
    saved.value = true
  },
})
function resetFields() {
  fps.value = ''
  confidence.value = ''
}
function save() {
  const target = String(fps.value).trim() === '' ? null : Number(fps.value)
  const score = String(confidence.value).trim() === '' ? null : Number(confidence.value)
  if (
    (target !== null && (!Number.isFinite(target) || target < 1 || target > 30)) ||
    (score !== null && (!Number.isFinite(score) || score <= 0 || score > 1))
  ) {
    invalid.value = true
    return
  }
  mutation.mutate({ id: props.cameraId, body: { target_fps: target, detection_confidence: score } })
}
</script>

<template>
  <section class="bg-card rounded-lg border p-5">
    <h2 class="text-sm font-semibold">{{ t('detection.title') }}</h2>
    <p class="text-muted-foreground mt-1 text-xs">{{ t('detection.hint') }}</p>
    <p v-if="query.isPending.value" class="mt-4 text-sm" role="status">
      {{ t('detection.loading') }}
    </p>
    <div v-else-if="query.isError.value" class="mt-4 text-sm" role="alert">
      {{ t('detection.loadError') }}
      <Button variant="outline" size="sm" @click="query.refetch()">{{
        t('detection.retry')
      }}</Button>
    </div>
    <form v-else-if="query.data.value" class="mt-5 space-y-4" @submit.prevent="save">
      <div class="space-y-1.5">
        <label :for="`fps-${cameraId}`" class="block text-xs font-medium">{{
          t('detection.fps')
        }}</label>
        <input
          :id="`fps-${cameraId}`"
          v-model="fps"
          type="number"
          min="1"
          max="30"
          step="any"
          :placeholder="String(query.data.value.defaults.target_fps)"
          class="bg-background w-full rounded-md border px-3 py-2 text-sm"
          :disabled="mutation.isPending.value"
        />
        <p class="text-muted-foreground text-xs">
          {{ t('detection.default', { n: query.data.value.defaults.target_fps }) }}
        </p>
      </div>
      <div class="space-y-1.5">
        <label :for="`confidence-${cameraId}`" class="block text-xs font-medium">{{
          t('detection.confidence')
        }}</label>
        <input
          :id="`confidence-${cameraId}`"
          v-model="confidence"
          type="number"
          min="0"
          max="1"
          step="any"
          :placeholder="String(query.data.value.defaults.detection_confidence)"
          class="bg-background w-full rounded-md border px-3 py-2 text-sm"
          :disabled="mutation.isPending.value"
        />
        <p class="text-muted-foreground text-xs">
          {{ t('detection.default', { n: query.data.value.defaults.detection_confidence }) }}
        </p>
      </div>
      <p v-if="invalid" class="text-critical text-xs" role="alert">{{ t('detection.invalid') }}</p>
      <p v-if="mutation.isError.value" class="text-critical text-xs" role="alert">
        {{ t(errorMessageKey(mutation.error.value)) }}
      </p>
      <p v-if="saved" class="text-xs" role="status">{{ t('detection.saved') }}</p>
      <div class="flex flex-wrap gap-2">
        <Button type="submit" size="sm" :disabled="mutation.isPending.value">{{
          t(mutation.isPending.value ? 'detection.saving' : 'detection.save')
        }}</Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          :disabled="mutation.isPending.value"
          @click="resetFields"
          >{{ t('detection.reset') }}</Button
        >
      </div>
    </form>
  </section>
</template>
