<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { use } from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, AriaComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import { init, type EChartsCoreOption, type EChartsType } from 'echarts/core'
use([
  LineChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  AriaComponent,
  SVGRenderer,
])
const props = defineProps<{ option: EChartsCoreOption; label: string }>()
const root = ref<HTMLElement | null>(null)
let chart: EChartsType | undefined
let observer: ResizeObserver | undefined
function apply(option: EChartsCoreOption) {
  chart?.setOption(
    { ...option, aria: { enabled: true, label: { description: props.label } } },
    true,
  )
}
onMounted(() => {
  if (!root.value) return
  chart = init(root.value, undefined, { renderer: 'svg' })
  apply(props.option)
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(root.value)
})
watch(
  () => props.option,
  (option) => apply(option),
  { deep: true },
)
onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>
<template><div ref="root" role="img" :aria-label="label" class="h-64 w-full min-w-0" /></template>
