<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery, useInfiniteQuery } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/layout/PageHeader.vue'
import AnalyticsChart from '@/components/analytics/AnalyticsChart.vue'
import TrackTimeline from '@/components/analytics/TrackTimeline.vue'
import { Button } from '@/components/ui/button'
import { fetchDashboard, fetchTracks } from '@/api/analytics'
import { eventTrend, eventBars, peopleTrend } from '@/lib/analytics'
const { t } = useI18n()
const hours = ref(24),
  cameraId = ref(''),
  end = ref(new Date().toISOString())
const filter = computed(() => ({
  start: new Date(Date.parse(end.value) - hours.value * 3600000).toISOString(),
  end: end.value,
  cameraId: cameraId.value,
}))
const query = useQuery({
  queryKey: computed(() => ['analytics', filter.value]),
  queryFn: ({ signal }) => fetchDashboard(filter.value, signal),
  retry: false,
})
const tracks = useInfiniteQuery({
  queryKey: computed(() => ['analytics-tracks', filter.value]),
  initialPageParam: undefined as string | undefined,
  queryFn: ({ pageParam, signal }) => fetchTracks(filter.value, pageParam, signal),
  getNextPageParam: (last) => last.next_cursor ?? undefined,
  retry: false,
})
const data = query.data
const catalog = useQuery({
  queryKey: ['analytics', 'camera-catalog'],
  queryFn: ({ signal }) => fetchDashboard({ ...filter.value, cameraId: '' }, signal),
  retry: false,
})
const rows = computed(() => tracks.data.value?.pages.flatMap((p) => p.items) ?? [])
const number = (n: number | null | undefined, digits = 0) =>
  n == null ? '—' : n.toLocaleString('ru-RU', { maximumFractionDigits: digits })
const typeName = (value: string) =>
  value === 'PERSON_CROSSED_LINE'
    ? t('lines.crossed')
    : value === 'PERSON_ENTERED_DANGER_ZONE'
      ? t('events.entered')
      : value === 'PERSON_LOITERING_IN_DANGER_ZONE'
        ? t('events.loitering')
        : value
const cards = computed(() =>
  data.value
    ? ([
        ['total', data.value.total_events],
        ['critical', data.value.critical_events],
        ['fp', data.value.false_positives],
        ['active', data.value.active_cameras],
        ['average', data.value.average_events_per_camera],
        ['people', data.value.completed_tracks],
      ] as const)
    : [],
)
const trend = computed(() => (data.value ? eventTrend(data.value, t('analytics.events')) : {}))
const byCamera = computed(() =>
  data.value
    ? eventBars(
        data.value.by_camera.map((c) => c.name),
        data.value.by_camera.map((c) => c.events),
        t('analytics.events'),
      )
    : {},
)
const byType = computed(() =>
  data.value
    ? eventBars(
        data.value.by_type.map((c) => typeName(c.key)),
        data.value.by_type.map((c) => c.count),
        t('analytics.events'),
      )
    : {},
)
const people = computed(() =>
  data.value ? peopleTrend(data.value, [t('analytics.persons'), t('analytics.inZone')]) : {},
)
function retry() {
  void query.refetch()
  void catalog.refetch()
}
function refresh() {
  end.value = new Date().toISOString()
  void catalog.refetch()
}
</script>
<template>
  <PageHeader :title="t('nav.analytics')"
    ><template #actions
      ><Button variant="outline" :disabled="query.isFetching.value" @click="refresh">{{
        t('analytics.refresh')
      }}</Button></template
    ></PageHeader
  >
  <section class="bg-card mb-5 flex flex-wrap gap-4 rounded-lg border p-4">
    <label class="space-y-1 text-xs"
      >{{ t('analytics.period')
      }}<select v-model="hours" class="bg-background block rounded border p-2">
        <option :value="1">{{ t('analytics.hour') }}</option>
        <option :value="24">{{ t('analytics.day') }}</option>
        <option :value="168">{{ t('analytics.week') }}</option>
      </select></label
    >
    <label class="min-w-0 space-y-1 text-xs"
      >{{ t('events.camera')
      }}<select v-model="cameraId" class="bg-background block max-w-full rounded border p-2">
        <option value="">{{ t('events.allCameras') }}</option>
        <option
          v-for="c in catalog.data.value?.by_camera ?? []"
          :key="c.camera_id"
          :value="c.camera_id"
        >
          {{ c.name }}{{ c.archived ? ` (${t('analytics.archived')})` : '' }}
        </option>
      </select></label
    >
    <p class="text-muted-foreground self-end text-xs">
      {{ t('analytics.window') }}: {{ new Date(filter.start).toLocaleString('ru-RU') }} —
      {{ new Date(filter.end).toLocaleString('ru-RU') }}
    </p>
  </section>
  <p class="text-muted-foreground mb-4 text-xs">{{ t('analytics.scope') }}</p>
  <p v-if="query.isPending.value" role="status">{{ t('detection.loading') }}</p>
  <div v-if="query.isError.value" role="alert" class="mb-4 space-y-3 rounded border p-4">
    <p>{{ t('analytics.error') }}</p>
    <Button variant="outline" @click="retry">{{ t('events.retry') }}</Button>
  </div>
  <template v-if="data">
    <p v-if="query.isFetching.value" role="status" class="text-muted-foreground mb-2 text-xs">
      {{ t('analytics.updating') }}
    </p>
    <div class="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      <article v-for="[key, value] in cards" :key="key" class="bg-card rounded-lg border p-4">
        <h2 class="text-muted-foreground text-xs">{{ t(`analytics.kpi.${key}`) }}</h2>
        <p class="mt-2 text-2xl font-semibold tabular-nums">
          {{ number(value, key === 'average' ? 2 : 0) }}
        </p>
      </article>
    </div>
    <div class="mb-5 grid min-w-0 gap-4 xl:grid-cols-2">
      <section class="bg-card min-w-0 rounded-lg border p-4 xl:col-span-2">
        <h2 class="font-semibold">{{ t('analytics.overTime') }}</h2>
        <AnalyticsChart :option="trend" :label="t('analytics.overTime')" />
        <p v-if="!data.total_events" class="text-muted-foreground text-xs">
          {{ t('analytics.noEvents') }}
        </p>
      </section>
      <section class="bg-card min-w-0 rounded-lg border p-4">
        <h2 class="font-semibold">{{ t('analytics.byCamera') }}</h2>
        <AnalyticsChart :option="byCamera" :label="t('analytics.byCamera')" />
      </section>
      <section class="bg-card min-w-0 rounded-lg border p-4">
        <h2 class="font-semibold">{{ t('analytics.byType') }}</h2>
        <AnalyticsChart
          v-if="data.by_type.length"
          :option="byType"
          :label="t('analytics.byType')"
        />
        <p v-else class="text-muted-foreground mt-4 text-xs">{{ t('analytics.noEvents') }}</p>
      </section>
    </div>
    <section class="bg-card mb-5 min-w-0 rounded-lg border p-4">
      <h2 class="font-semibold">{{ t('analytics.cameras') }}</h2>
      <p class="text-muted-foreground mt-2 text-xs">{{ t('analytics.sampleHint') }}</p>
      <div class="mt-4 space-y-3">
        <article v-for="c in data.by_camera" :key="c.camera_id" class="rounded border p-3 text-sm">
          <div class="flex flex-wrap justify-between gap-2">
            <strong class="break-words"
              >{{ c.name }} {{ c.archived ? `(${t('analytics.archived')})` : '' }}</strong
            ><RouterLink
              v-if="!c.archived"
              :to="`/monitoring/${c.camera_id}`"
              class="text-primary underline"
              >{{ t('analytics.open') }}</RouterLink
            >
          </div>
          <dl class="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-3 xl:grid-cols-5">
            <div>
              <dt>{{ t('analytics.events') }}</dt>
              <dd>{{ number(c.events) }}</dd>
            </div>
            <div>
              <dt>{{ t('analytics.observed') }}</dt>
              <dd>{{ number(c.observed_seconds, 1) }} {{ t('snapshots.seconds') }}</dd>
            </div>
            <div>
              <dt>{{ t('analytics.mean') }}</dt>
              <dd>{{ number(c.average_persons, 2) }}</dd>
            </div>
            <div>
              <dt>{{ t('analytics.max') }}</dt>
              <dd>{{ number(c.max_persons) }}</dd>
            </div>
            <div>
              <dt>{{ t('analytics.completed') }}</dt>
              <dd>{{ number(c.completed_tracks) }}</dd>
            </div>
          </dl>
        </article>
      </div>
    </section>
    <section class="bg-card mb-5 min-w-0 rounded-lg border p-4">
      <h2 class="font-semibold">{{ t('analytics.occupancy') }}</h2>
      <p v-if="!cameraId" class="text-muted-foreground mt-3 text-sm">
        {{ t('analytics.selectCamera') }}
      </p>
      <template v-else>
        <p class="text-muted-foreground mt-2 text-xs">
          {{ t('analytics.bucketHint', { n: data.bucket_seconds }) }}
        </p>
        <AnalyticsChart
          v-if="data.people_over_time.length"
          :option="people"
          :label="t('analytics.occupancy')"
        />
        <p v-else class="text-muted-foreground mt-3 text-sm">
          {{ t('analytics.noSamples') }}
        </p></template
      >
    </section>
  </template>
  <section class="bg-card min-w-0 space-y-3 rounded-lg border p-4">
    <h2 class="font-semibold">{{ t('analytics.timeline') }}</h2>
    <p class="text-muted-foreground text-xs">{{ t('analytics.trackHint') }}</p>
    <p class="text-xs">
      <span class="text-emerald-600">■ {{ t('analytics.states.NORMAL') }}</span> ·
      <span class="text-red-500">■ {{ t('analytics.states.IN_DANGER_ZONE') }}</span> ·
      <span class="text-slate-400">■ {{ t('analytics.states.LOST') }}</span>
    </p>
    <p v-if="tracks.isPending.value" role="status">{{ t('detection.loading') }}</p>
    <div v-else-if="tracks.isError.value" role="alert">
      <p>{{ t('analytics.error') }}</p>
      <Button variant="outline" @click="tracks.refetch()">{{ t('events.retry') }}</Button>
    </div>
    <p v-else-if="!rows.length" class="text-muted-foreground text-sm">
      {{ t('analytics.noTracks') }}
    </p>
    <TrackTimeline v-for="track in rows" :key="track.id" :track="track" /><Button
      v-if="tracks.hasNextPage.value"
      :disabled="tracks.isFetching.value"
      variant="outline"
      @click="tracks.fetchNextPage()"
      >{{ t('events.more') }}</Button
    >
  </section>
</template>
