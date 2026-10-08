<script setup lang="ts">
defineProps<{ title: string }>()
</script>

<template>
  <div class="mb-4 flex min-h-9 items-center justify-between gap-4">
    <h1 class="text-lg font-semibold tracking-tight">{{ title }}</h1>
    <slot name="actions" />
  </div>
</template>
