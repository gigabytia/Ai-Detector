<script setup lang="ts">
import { Moon, Sun } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const { t } = useI18n()
</script>

<template>
  <Button variant="ghost" size="icon" :aria-label="t('theme.toggle')" @click="ui.toggleTheme()">
    <Moon v-if="ui.theme === 'light'" class="size-4" aria-hidden="true" />
    <Sun v-else class="size-4" aria-hidden="true" />
  </Button>
</template>
