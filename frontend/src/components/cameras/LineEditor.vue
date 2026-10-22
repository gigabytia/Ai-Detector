<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'
import { fetchLines, saveLine, deleteLine } from '@/api/lines'
import type { Point } from '@/api/zones'
import { Button } from '@/components/ui/button'
import { ApiError } from '@/api/http'
import { errorMessageKey } from '@/lib/apiErrors'
const props = defineProps<{
  cameraId: string
  points: Point[]
  editing: boolean
  blocked?: boolean
}>()
const emit = defineEmits<{
  'update:points': [points: Point[]]
  'update:editing': [value: boolean]
}>()
const { t } = useI18n()
const client = useQueryClient()
const query = useQuery({
  queryKey: computed(() => ['lines', props.cameraId]),
  queryFn: ({ signal }) => fetchLines(props.cameraId, signal),
  refetchOnWindowFocus: false,
})
const line = computed(() => query.data.value?.[0])
const editingId = ref<string | undefined>(undefined)
const deletingId = ref<string | undefined>(undefined)
const name = ref('')
const enabled = ref(true)
const x = ref('')
const y = ref('')
const invalid = ref(false)
const saved = ref(false)
const confirming = ref(false)
const mutation = useMutation({
  mutationFn: async (remove: boolean) => {
    if (remove && deletingId.value) await deleteLine(props.cameraId, deletingId.value)
    else
      await saveLine(
        props.cameraId,
        {
          name: name.value.trim(),
          enabled: enabled.value,
          p1: props.points[0]!,
          p2: props.points[1]!,
        },
        editingId.value,
      )
  },
  onSuccess: async () => {
    emit('update:editing', false)
    emit('update:points', [])
    confirming.value = false
    await client.invalidateQueries({ queryKey: ['lines', props.cameraId] })
    saved.value = true
  },
})
watch(
  () => props.cameraId,
  () => {
    emit('update:editing', false)
    emit('update:points', [])
    mutation.reset()
    saved.value = false
  },
)
function start() {
  editingId.value = line.value?.id
  name.value = line.value?.name ?? t('lines.title')
  enabled.value = line.value?.enabled ?? true
  emit('update:points', line.value ? [{ ...line.value.p1 }, { ...line.value.p2 }] : [])
  emit('update:editing', true)
  invalid.value = false
  saved.value = false
  mutation.reset()
  confirming.value = false
}
function confirmDelete() {
  deletingId.value = line.value?.id
  confirming.value = !confirming.value
}
function cancel() {
  emit('update:editing', false)
  emit('update:points', [])
  invalid.value = false
  mutation.reset()
}
function addPoint() {
  const px = Number(x.value),
    py = Number(y.value)
  if (
    String(x.value).trim() === '' ||
    String(y.value).trim() === '' ||
    !Number.isFinite(px) ||
    !Number.isFinite(py) ||
    px < 0 ||
    px > 1 ||
    py < 0 ||
    py > 1 ||
    props.points.length >= 2
  ) {
    invalid.value = true
    return
  }
  emit('update:points', [...props.points, { x: px, y: py }])
  invalid.value = false
  x.value = ''
  y.value = ''
}
function save() {
  if (
    !name.value.trim() ||
    props.points.length !== 2 ||
    Math.hypot(props.points[0]!.x - props.points[1]!.x, props.points[0]!.y - props.points[1]!.y) <=
      1e-6
  ) {
    invalid.value = true
    return
  }
  invalid.value = false
  mutation.mutate(false)
}
</script>
<template>
  <section class="bg-card rounded-lg border p-5">
    <h2 class="text-sm font-semibold">{{ t('lines.title') }}</h2>
    <p v-if="query.isPending.value" class="mt-3 text-xs" role="status">
      {{ t('detection.loading') }}
    </p>
    <div v-else-if="query.isError.value" role="alert" class="mt-3 text-xs">
      {{ t('lines.loadError') }}
      <Button size="sm" variant="outline" @click="query.refetch()">{{
        t('detection.retry')
      }}</Button>
    </div>
    <template v-else>
      <p v-if="(query.data.value?.length ?? 0) > 1" class="text-muted-foreground mt-3 text-xs">
        {{ t('lines.many') }}
      </p>
      <template v-if="!editing">
        <p class="mt-3 text-sm">{{ line?.name ?? t('lines.empty') }}</p>
        <div class="mt-3 flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            :disabled="mutation.isPending.value || blocked"
            @click="start"
            >{{ t(line ? 'lines.edit' : 'lines.create') }}</Button
          >
          <Button
            v-if="line"
            size="sm"
            variant="outline"
            :disabled="mutation.isPending.value || blocked"
            @click="confirmDelete"
            >{{ t('lines.delete') }}</Button
          >
          <Button
            v-if="confirming"
            size="sm"
            :disabled="mutation.isPending.value"
            @click="mutation.mutate(true)"
            >{{ t('lines.confirm') }}</Button
          >
        </div>
      </template>
      <form v-else class="mt-3 space-y-3" @submit.prevent="save">
        <p class="text-muted-foreground text-xs">{{ t('lines.hint') }}</p>
        <p class="text-muted-foreground text-xs">{{ t('lines.frameHint') }}</p>
        <label class="block text-xs"
          >{{ t('lines.name')
          }}<input
            v-model="name"
            maxlength="100"
            required
            :disabled="mutation.isPending.value"
            class="bg-background mt-1 w-full rounded border p-2 text-sm"
        /></label>
        <label class="flex items-center gap-2 text-xs"
          ><input v-model="enabled" type="checkbox" :disabled="mutation.isPending.value" />{{
            t('lines.enabled')
          }}</label
        >
        <p class="text-xs" role="status">{{ t('lines.points', { n: points.length }) }}</p>
        <div class="flex gap-2">
          <label class="min-w-0 flex-1 text-xs"
            >{{ t('lines.x')
            }}<input
              v-model="x"
              type="number"
              min="0"
              max="1"
              step="any"
              class="bg-background mt-1 w-full rounded border p-2"
              :disabled="mutation.isPending.value"
          /></label>
          <label class="min-w-0 flex-1 text-xs"
            >{{ t('lines.y')
            }}<input
              v-model="y"
              type="number"
              min="0"
              max="1"
              step="any"
              class="bg-background mt-1 w-full rounded border p-2"
              :disabled="mutation.isPending.value"
          /></label>
        </div>
        <div class="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            :disabled="mutation.isPending.value || points.length >= 2"
            @click="addPoint"
            >{{ t('lines.addPoint') }}</Button
          >
          <Button
            type="button"
            size="sm"
            variant="outline"
            :disabled="mutation.isPending.value || !points.length"
            @click="emit('update:points', points.slice(0, -1))"
            >{{ t('lines.undo') }}</Button
          >
          <Button
            type="button"
            size="sm"
            variant="outline"
            :disabled="mutation.isPending.value"
            @click="emit('update:points', [])"
            >{{ t('lines.clear') }}</Button
          >
        </div>
        <div class="flex flex-wrap gap-2">
          <Button size="sm" type="submit" :disabled="mutation.isPending.value">{{
            t('lines.save')
          }}</Button>
          <Button
            size="sm"
            type="button"
            variant="outline"
            :disabled="mutation.isPending.value"
            @click="cancel"
            >{{ t('lines.cancel') }}</Button
          >
        </div>
      </form>
      <p v-if="invalid || mutation.isError.value" class="text-critical mt-3 text-xs" role="alert">
        {{
          invalid ||
          (mutation.error.value instanceof ApiError && mutation.error.value.status === 422)
            ? t('lines.invalid')
            : t(errorMessageKey(mutation.error.value))
        }}
      </p>
      <p v-if="saved" class="mt-3 text-xs" role="status">{{ t('lines.saved') }}</p>
    </template>
  </section>
</template>
