import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import {
  type CameraAction,
  type CameraCreate,
  type CameraUpdate,
  createCamera,
  deleteCamera,
  fetchCameras,
  runCameraAction,
  updateCamera,
} from '@/api/cameras'
import { errorMessageKey } from '@/lib/apiErrors'

// Polling until live status arrives over SSE (Milestone 7).
const REFRESH_INTERVAL_MS = 2_000
const CAMERAS_KEY = ['cameras'] as const

export function useCameras() {
  return useQuery({
    queryKey: CAMERAS_KEY,
    queryFn: ({ signal }) => fetchCameras(signal),
    refetchInterval: REFRESH_INTERVAL_MS,
  })
}

export function useCameraMutations() {
  const client = useQueryClient()
  const { t } = useI18n()
  const refresh = () => client.invalidateQueries({ queryKey: CAMERAS_KEY })
  const fail = (error: unknown) => toast.error(t(errorMessageKey(error)))

  const create = useMutation({
    mutationFn: (body: CameraCreate) => createCamera(body),
    onSuccess: (camera) => toast.success(t('cameras.toast.created', { name: camera.name })),
    onSettled: refresh,
  })
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: CameraUpdate }) => updateCamera(id, body),
    onSuccess: () => toast.success(t('cameras.toast.updated')),
    onSettled: refresh,
  })
  const remove = useMutation({
    mutationFn: (id: string) => deleteCamera(id),
    onSuccess: () => toast.success(t('cameras.toast.deleted')),
    onError: fail,
    onSettled: refresh,
  })
  const action = useMutation({
    mutationFn: ({ id, action }: { id: string; action: CameraAction }) =>
      runCameraAction(id, action),
    onSuccess: (_camera, { action }) => toast.success(t(`cameras.toast.${action}`)),
    onError: fail,
    onSettled: refresh,
  })
  return { create, update, remove, action }
}
