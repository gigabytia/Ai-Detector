<script setup lang="ts">
import { Pencil, Play, Plus, RotateCw, Square, Trash2 } from '@lucide/vue'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Camera } from '@/api/cameras'
import CameraFormDialog from '@/components/cameras/CameraFormDialog.vue'
import CameraRuntimeDetails from '@/components/cameras/CameraRuntimeDetails.vue'
import CamerasEmptyState from '@/components/cameras/CamerasEmptyState.vue'
import CameraStatusBadge from '@/components/cameras/CameraStatusBadge.vue'
import PageHeader from '@/components/layout/PageHeader.vue'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { useCameraMutations, useCameras } from '@/composables/useCameras'

const { t } = useI18n()
const { data: cameras, isPending, isError } = useCameras()
const { remove, action } = useCameraMutations()

const formOpen = ref(false)
const editing = ref<Camera | null>(null)
const deleting = ref<Camera | null>(null)
const deleteOpen = ref(false)

function askDelete(camera: Camera) {
  deleting.value = camera
  deleteOpen.value = true
}

function openCreate() {
  editing.value = null
  formOpen.value = true
}

function openEdit(camera: Camera) {
  editing.value = camera
  formOpen.value = true
}

// The dialog closes itself on confirm; `deleting` is kept so the handler still sees it.
function confirmDelete() {
  if (deleting.value) remove.mutate(deleting.value.id)
}

function isBusy(camera: Camera): boolean {
  return action.isPending.value && action.variables.value?.id === camera.id
}
</script>

<template>
  <PageHeader :title="t('nav.cameras')">
    <template #actions>
      <Button v-if="cameras?.length" @click="openCreate">
        <Plus aria-hidden="true" />
        {{ t('cameras.add') }}
      </Button>
    </template>
  </PageHeader>

  <p v-if="isError && !cameras" class="text-critical text-sm" role="alert">
    {{ t('cameras.loadError') }}
  </p>
  <div v-else-if="isPending" class="space-y-2" aria-busy="true">
    <div v-for="i in 2" :key="i" class="bg-muted h-16 animate-pulse rounded-lg" />
  </div>
  <CamerasEmptyState v-else-if="cameras && cameras.length === 0">
    <Button class="mt-4" @click="openCreate">
      <Plus aria-hidden="true" />
      {{ t('cameras.add') }}
    </Button>
  </CamerasEmptyState>

  <ul v-else class="bg-card divide-y rounded-lg border">
    <li
      v-for="camera in cameras"
      :key="camera.id"
      class="flex flex-col gap-3 p-4 md:flex-row md:items-center"
    >
      <div class="min-w-0 flex-1 space-y-1">
        <div class="flex flex-wrap items-center gap-2">
          <span class="truncate font-medium">{{ camera.name }}</span>
          <CameraStatusBadge :camera="camera" />
        </div>
        <p class="text-muted-foreground truncate font-mono text-xs">
          {{ t(`cameras.source.${camera.source_type}`) }} · {{ camera.source_url }}
        </p>
        <CameraRuntimeDetails :camera="camera" />
      </div>

      <div class="flex shrink-0 gap-1">
        <Button
          v-if="!camera.enabled"
          variant="outline"
          size="sm"
          :disabled="isBusy(camera)"
          @click="action.mutate({ id: camera.id, action: 'start' })"
        >
          <Play aria-hidden="true" />
          {{ t('cameras.actions.start') }}
        </Button>
        <Button
          v-else
          variant="outline"
          size="sm"
          :disabled="isBusy(camera)"
          @click="action.mutate({ id: camera.id, action: 'stop' })"
        >
          <Square aria-hidden="true" />
          {{ t('cameras.actions.stop') }}
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          :disabled="isBusy(camera)"
          :title="t('cameras.actions.restart')"
          :aria-label="t('cameras.actions.restart')"
          @click="action.mutate({ id: camera.id, action: 'restart' })"
        >
          <RotateCw aria-hidden="true" />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          :title="t('cameras.actions.edit')"
          :aria-label="t('cameras.actions.edit')"
          @click="openEdit(camera)"
        >
          <Pencil aria-hidden="true" />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          class="text-critical"
          :title="t('cameras.actions.delete')"
          :aria-label="t('cameras.actions.delete')"
          @click="askDelete(camera)"
        >
          <Trash2 aria-hidden="true" />
        </Button>
      </div>
    </li>
  </ul>

  <CameraFormDialog v-model:open="formOpen" :camera="editing" />

  <AlertDialog v-model:open="deleteOpen">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>{{
          t('cameras.delete.title', { name: deleting?.name })
        }}</AlertDialogTitle>
        <AlertDialogDescription>{{ t('cameras.delete.description') }}</AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel>{{ t('common.cancel') }}</AlertDialogCancel>
        <AlertDialogAction
          class="bg-critical hover:bg-critical/90 text-white"
          @click="confirmDelete"
        >
          {{ t('cameras.actions.delete') }}
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
