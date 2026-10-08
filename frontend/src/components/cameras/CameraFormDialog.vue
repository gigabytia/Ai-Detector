<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { type Camera, type SourceType, uploadVideo } from '@/api/cameras'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useCameraMutations } from '@/composables/useCameras'
import { errorMessageKey } from '@/lib/apiErrors'

const props = defineProps<{ camera?: Camera | null }>()
const open = defineModel<boolean>('open', { required: true })
const { t } = useI18n()
const { create, update } = useCameraMutations()

const SCENARIOS = ['walk_through', 'two_people'] as const
const SOURCE_TYPES: SourceType[] = ['file', 'rtsp', 'mock']

const name = ref('')
const sourceType = ref<SourceType>('file')
const rtspUrl = ref('')
const scenario = ref<string>(SCENARIOS[0])
const file = ref<File | null>(null)
const startNow = ref(true)
const error = ref<string | null>(null)
const uploading = ref(false)

const editing = computed(() => Boolean(props.camera))
const busy = computed(() => uploading.value || create.isPending.value || update.isPending.value)

watch(open, (isOpen) => {
  if (!isOpen) return
  error.value = null
  file.value = null
  name.value = props.camera?.name ?? ''
  sourceType.value = (props.camera?.source_type as SourceType | undefined) ?? 'file'
  rtspUrl.value = ''
  const currentScenario = props.camera?.source_url.replace('mock://', '')
  scenario.value =
    SCENARIOS.find((item) => props.camera?.source_type === 'mock' && item === currentScenario) ??
    SCENARIOS[0]
  startNow.value = true
})

function onFileChange(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

async function resolveSourceUrl(): Promise<string | null> {
  if (sourceType.value === 'rtsp') return rtspUrl.value.trim() || null
  if (sourceType.value === 'mock') return `mock://${scenario.value}`
  if (!file.value) return null
  uploading.value = true
  try {
    return (await uploadVideo(file.value)).source_url
  } finally {
    uploading.value = false
  }
}

function sourceChanged(camera: Camera): boolean {
  if (sourceType.value === 'file') return file.value !== null
  if (sourceType.value === 'rtsp') return rtspUrl.value.trim() !== ''
  return camera.source_url !== `mock://${scenario.value}`
}

async function submit() {
  error.value = null
  const trimmed = name.value.trim()
  if (!trimmed) {
    error.value = t('cameras.form.nameRequired')
    return
  }
  try {
    if (props.camera) {
      // The source is changed only when the operator provides a new one.
      const sourceUrl = sourceChanged(props.camera) ? await resolveSourceUrl() : null
      await update.mutateAsync({
        id: props.camera.id,
        body: sourceUrl
          ? { name: trimmed, source_type: sourceType.value, source_url: sourceUrl }
          : { name: trimmed },
      })
    } else {
      const sourceUrl = await resolveSourceUrl()
      if (!sourceUrl) {
        error.value = t(`cameras.form.sourceRequired.${sourceType.value}`)
        return
      }
      await create.mutateAsync({
        name: trimmed,
        source_type: sourceType.value,
        source_url: sourceUrl,
        enabled: startNow.value,
      })
    }
    open.value = false
  } catch (exc) {
    error.value = t(errorMessageKey(exc))
  }
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="sm:max-w-lg">
      <DialogHeader>
        <DialogTitle>{{
          editing ? t('cameras.form.editTitle') : t('cameras.form.createTitle')
        }}</DialogTitle>
        <DialogDescription>{{ t('cameras.form.description') }}</DialogDescription>
      </DialogHeader>

      <form id="camera-form" class="space-y-4" @submit.prevent="submit">
        <div class="space-y-1.5">
          <Label for="camera-name">{{ t('cameras.form.name') }}</Label>
          <Input
            id="camera-name"
            v-model="name"
            maxlength="100"
            :placeholder="t('cameras.form.namePlaceholder')"
            autocomplete="off"
          />
        </div>

        <fieldset class="space-y-1.5">
          <legend class="text-sm font-medium">{{ t('cameras.form.sourceType') }}</legend>
          <div class="grid grid-cols-3 gap-2" role="radiogroup">
            <label
              v-for="type in SOURCE_TYPES"
              :key="type"
              class="has-checked:border-primary has-checked:bg-accent cursor-pointer rounded-md border px-3 py-2 text-sm"
            >
              <input
                v-model="sourceType"
                class="sr-only"
                type="radio"
                name="source-type"
                :value="type"
              />
              <span class="font-medium">{{ t(`cameras.source.${type}`) }}</span>
              <span class="text-muted-foreground block text-xs">{{
                t(`cameras.sourceHint.${type}`)
              }}</span>
            </label>
          </div>
        </fieldset>

        <p v-if="editing" class="text-muted-foreground text-xs">
          {{ t('cameras.form.keepSource', { url: camera?.source_url }) }}
        </p>

        <div v-if="sourceType === 'file'" class="space-y-1.5">
          <Label for="camera-file">{{ t('cameras.form.file') }}</Label>
          <Input
            id="camera-file"
            type="file"
            accept=".mp4,.mov,.mkv,.avi,video/*"
            @change="onFileChange"
          />
          <p class="text-muted-foreground text-xs">{{ t('cameras.form.fileHint') }}</p>
        </div>
        <div v-else-if="sourceType === 'rtsp'" class="space-y-1.5">
          <Label for="camera-rtsp">{{ t('cameras.form.rtspUrl') }}</Label>
          <Input
            id="camera-rtsp"
            v-model="rtspUrl"
            placeholder="rtsp://user:password@192.168.1.10:554/stream1"
            autocomplete="off"
            spellcheck="false"
          />
          <p class="text-muted-foreground text-xs">{{ t('cameras.form.rtspHint') }}</p>
        </div>
        <div v-else class="space-y-1.5">
          <Label for="camera-scenario">{{ t('cameras.form.scenario') }}</Label>
          <select
            id="camera-scenario"
            v-model="scenario"
            class="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
          >
            <option v-for="item in SCENARIOS" :key="item" :value="item">
              {{ t(`cameras.scenario.${item}`) }}
            </option>
          </select>
        </div>

        <div v-if="!editing" class="flex items-center gap-2">
          <Checkbox id="camera-start" v-model="startNow" />
          <Label for="camera-start" class="font-normal">{{ t('cameras.form.startNow') }}</Label>
        </div>

        <p v-if="error" class="text-critical text-sm" role="alert">{{ error }}</p>
      </form>

      <DialogFooter>
        <Button variant="outline" :disabled="busy" @click="open = false">
          {{ t('common.cancel') }}
        </Button>
        <Button type="submit" form="camera-form" :disabled="busy">
          {{
            uploading
              ? t('cameras.form.uploading')
              : editing
                ? t('common.save')
                : t('cameras.form.create')
          }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
