<script setup lang="ts">
import AppShell from '@/components/layout/AppShell.vue'
import { Toaster } from '@/components/ui/sonner'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
</script>

<template>
  <AppShell>
    <RouterView />
  </AppShell>
  <Toaster :theme="ui.theme" position="bottom-right" rich-colors close-button />
</template>
