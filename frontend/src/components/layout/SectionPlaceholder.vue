<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <p class="text-muted-foreground text-sm">{{ t('placeholder') }}</p>
</template>
