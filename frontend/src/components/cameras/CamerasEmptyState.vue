<script setup lang="ts">
import { Cctv } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

defineProps<{ actionLabel?: string }>()
defineEmits<{ action: [] }>()
const { t } = useI18n()
</script>

<template>
  <div
    class="bg-card flex flex-col items-center rounded-lg border border-dashed px-6 py-12 text-center"
  >
    <Cctv class="text-muted-foreground mb-3 size-8" aria-hidden="true" />
    <p class="font-medium">{{ t('cameras.empty.title') }}</p>
    <p class="text-muted-foreground mt-1 text-sm">{{ t('cameras.empty.hint') }}</p>
    <slot />
  </div>
</template>
