<!-- frontend/src/components/LineChart.vue -->
<template>
  <div class="card">
    <div class="title">{{ title }}</div>

    <div v-if="hasData" class="row">
      <svg class="svg" :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none">
        <!-- background -->
        <rect :x="0" :y="0" :width="W" :height="H" fill="white" />
        <rect :x="ML" :y="MT" :width="PW" :height="PH" fill="white" stroke="#e5e7eb" />

        <!-- grid Y -->
        <g v-for="t in yTicks" :key="'yg' + t.v">
          <line
            :x1="ML" :x2="ML + PW"
            :y1="yScale(t.v)" :y2="yScale(t.v)"
            stroke="#f3f4f6"
          />
        </g>

        <!-- axes -->
        <line :x1="ML" :y1="MT" :x2="ML" :y2="MT + PH" stroke="#9ca3af" />
        <line :x1="ML" :y1="MT + PH" :x2="ML + PW" :y2="MT + PH" stroke="#9ca3af" />

        <!-- y ticks + labels -->
        <g v-for="t in yTicks" :key="'y' + t.v">
          <line
            :x1="ML - 4" :x2="ML"
            :y1="yScale(t.v)" :y2="yScale(t.v)"
            stroke="#6b7280"
          />
          <text
            :x="ML - 8"
            :y="yScale(t.v) + 4"
            text-anchor="end"
            font-size="12"
            fill="#374151"
          >{{ t.label }}</text>
        </g>

        <!-- x ticks + labels -->
        <g v-for="t in xTicks" :key="'x' + t.v">
          <line
            :x1="xScale(t.v)" :x2="xScale(t.v)"
            :y1="MT + PH" :y2="MT + PH + 4"
            stroke="#6b7280"
          />
          <text
            :x="xScale(t.v)"
            :y="MT + PH + 18"
            text-anchor="middle"
            font-size="12"
            fill="#374151"
          >{{ t.label }}</text>
        </g>

        <!-- y axis label -->
        <text
          :x="14"
          :y="MT + PH / 2"
          font-size="12"
          fill="#374151"
          text-anchor="middle"
          :transform="`rotate(-90 14 ${MT + PH / 2})`"
        >{{ yLabel }}</text>

        <!-- x axis label -->
        <text
          :x="ML + PW / 2"
          :y="H - 6"
          font-size="12"
          fill="#374151"
          text-anchor="middle"
        >{{ xLabel }}</text>

        <!-- series paths -->
        <path
          v-for="s in series"
          :key="s.name"
          :d="pathFor(s.values)"
          fill="none"
          :stroke="s.color"
          stroke-width="2"
          stroke-linejoin="round"
          stroke-linecap="round"
        />
      </svg>

      <!-- legend -->
      <div class="legend">
        <div v-for="s in series" :key="'leg' + s.name" class="leg-item">
          <span class="swatch" :style="{ background: s.color }"></span>
          <span class="leg-text">{{ s.name }}</span>
        </div>
      </div>
    </div>

    <!-- empty state -->
    <div v-else class="empty-state">
      Нет данных для отображения
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  title:   { type: String, default: "" },
  xLabel:  { type: String, default: "Время (сек)" },
  yLabel:  { type: String, default: "Количество" },
  xValues: { type: Array,  default: () => [] },
  series:  { type: Array,  default: () => [] },
  yMax:    { type: Number, default: null },
});

const W  = 980;
const H  = 260;
const ML = 56;
const MR = 10;
const MT = 14;
const MB = 44;
const PW = W - ML - MR;
const PH = H - MT - MB;

// ── helpers ──────────────────────────────────────────────
function toNum(x) {
  const v = Number(x);
  return Number.isFinite(v) ? v : 0;
}

// ── data validity ─────────────────────────────────────────
const hasData = computed(() =>
  props.xValues.length > 0 &&
  props.series.some(s => s.values && s.values.length > 0)
);

// ── domain ────────────────────────────────────────────────
const xNums = computed(() => props.xValues.map(toNum));

const xMin = computed(() => {
  if (!xNums.value.length) return 0;
  return Math.min(...xNums.value);
});

const xMax = computed(() => {
  if (!xNums.value.length) return 1;
  const m = Math.max(...xNums.value);
  return m === xMin.value ? xMin.value + 1 : m;
});

const yMaxAuto = computed(() => {
  let m = 0;
  for (const s of props.series) {
    for (const v of (s.values || [])) m = Math.max(m, toNum(v));
  }
  return Math.max(1, m);
});

const yMaxEff = computed(() => {
  if (props.yMax != null && Number.isFinite(Number(props.yMax))) {
    return Math.max(1e-6, Number(props.yMax));
  }
  return yMaxAuto.value;
});

// ── scales ────────────────────────────────────────────────
function xScale(t) {
  const denom = Math.max(1e-6, xMax.value - xMin.value);
  return ML + ((toNum(t) - xMin.value) / denom) * PW;
}

function yScale(v) {
  return MT + PH - (toNum(v) / Math.max(1e-6, yMaxEff.value)) * PH;
}

// ── path builder ──────────────────────────────────────────
function pathFor(values) {
  if (!values || !values.length || !xNums.value.length) return "";
  const n = Math.min(values.length, xNums.value.length);
  let d = "";
  for (let i = 0; i < n; i++) {
    const x = xScale(xNums.value[i]);
    const y = yScale(values[i]);
    d += i === 0 ? `M ${x} ${y}` : ` L ${x} ${y}`;
  }
  return d;
}

// ── ticks ─────────────────────────────────────────────────
function makeTicks(minV, maxV, count, decimals = 0) {
  if (count <= 1) return [{ v: minV, label: Number(minV).toFixed(decimals) }];
  const out = [];
  for (let i = 0; i < count; i++) {
    const v = minV + (i * (maxV - minV)) / (count - 1);
    out.push({ v, label: v.toFixed(decimals) });
  }
  return out;
}

const xTicks = computed(() => {
  const range = xMax.value - xMin.value;
  const decimals = range < 10 ? 1 : 0;
  // адаптивное число тиков
  const count = Math.min(7, Math.max(2, Math.floor(PW / 120)));
  return makeTicks(xMin.value, xMax.value, count, decimals);
});

const yTicks = computed(() => makeTicks(0, yMaxEff.value, 4, 0));
</script>

<style scoped>
.card {
  max-width: 1180px;
  border: 1px solid #ddd;
  background: #fff;
  padding: 10px;
}
.title {
  font-weight: 700;
  margin-bottom: 8px;
}
.row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.svg {
  flex: 1;
  height: 260px;
  display: block;
}
.legend {
  width: 180px;
  padding-top: 6px;
  flex-shrink: 0;
}
.leg-item {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
  color: #111827;
}
.swatch {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  display: inline-block;
  border-radius: 2px;
}
.leg-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.empty-state {
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #9ca3af;
  font-size: 14px;
}
</style>