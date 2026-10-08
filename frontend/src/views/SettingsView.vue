<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import PageHeader from '@/components/layout/PageHeader.vue'
import SystemStatusPanel from '@/components/system/SystemStatusPanel.vue'

const { t } = useI18n()
</script>

<template>
  <PageHeader :title="t('nav.settings')" />
  <SystemStatusPanel />
</template>
