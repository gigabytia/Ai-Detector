<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import PageHeader from '@/components/layout/PageHeader.vue'
import SectionPlaceholder from '@/components/layout/SectionPlaceholder.vue'

const { t } = useI18n()
</script>

<template>
  <PageHeader :title="t('nav.analytics')" />
  <SectionPlaceholder />
</template>
