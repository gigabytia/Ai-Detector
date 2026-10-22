import type { EChartsCoreOption } from 'echarts/core'
import type { Dashboard } from '@/api/analytics'
// One unit per axis. Missing occupancy is null, not zero or interpolated.
export function eventTrend(data: Dashboard, name: string): EChartsCoreOption {
  return {
    animation: false,
    aria: { enabled: true },
    tooltip: { trigger: 'axis', renderMode: 'richText' },
    grid: { left: 45, right: 12, top: 20, bottom: 55 },
    xAxis: { type: 'time', axisLabel: { color: '#94a3b8' } },
    yAxis: { type: 'value', minInterval: 1, min: 0, axisLabel: { color: '#94a3b8' } },
    series: [
      {
        name,
        type: 'bar',
        itemStyle: { color: '#38bdf8' },
        data: data.events_over_time.map((b) => [b.at, b.events]),
      },
    ],
  }
}
export function eventBars(labels: string[], counts: number[], name: string): EChartsCoreOption {
  return {
    animation: false,
    aria: { enabled: true },
    tooltip: { trigger: 'axis', renderMode: 'richText' },
    grid: { left: 45, right: 12, top: 20, bottom: 75 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: {
        color: '#94a3b8',
        width: 90,
        overflow: 'truncate',
        rotate: labels.length > 4 ? 25 : 0,
      },
    },
    yAxis: { type: 'value', min: 0, minInterval: 1, axisLabel: { color: '#94a3b8' } },
    series: [{ name, type: 'bar', data: counts, itemStyle: { color: '#38bdf8' } }],
  }
}
export function peopleTrend(data: Dashboard, names: [string, string]): EChartsCoreOption {
  const samples = new Map(data.people_over_time.map((b) => [Date.parse(b.at), b]))
  return {
    animation: false,
    aria: { enabled: true },
    tooltip: { trigger: 'axis', renderMode: 'richText' },
    legend: { data: names, textStyle: { color: '#94a3b8' } },
    grid: { left: 45, right: 12, top: 40, bottom: 55 },
    xAxis: { type: 'time', axisLabel: { color: '#94a3b8' } },
    yAxis: { type: 'value', min: 0, axisLabel: { color: '#94a3b8' } },
    series: names.map((name, i) => ({
      name,
      type: 'line',
      showSymbol: false,
      connectNulls: false,
      itemStyle: { color: i ? '#f87171' : '#34d399' },
      data: data.events_over_time.map((b) => [
        b.at,
        samples.has(Date.parse(b.at))
          ? i
            ? samples.get(Date.parse(b.at))!.persons_in_zone
            : samples.get(Date.parse(b.at))!.persons
          : null,
      ]),
    })),
  }
}
