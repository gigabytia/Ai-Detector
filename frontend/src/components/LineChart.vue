<template>
  <div class="card">
    <div class="title">{{ title }}</div>

    <div class="row">
      <svg class="svg" :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none">
        <!-- background -->
        <rect :x="0" :y="0" :width="W" :height="H" fill="white" />
        <rect :x="ML" :y="MT" :width="PW" :height="PH" fill="white" stroke="#e5e7eb" />

        <!-- grid Y -->
        <g v-for="t in yTicks" :key="'yg'+t.v">
          <line
            :x1="ML" :x2="ML+PW"
            :y1="yScale(t.v)" :y2="yScale(t.v)"
            stroke="#f3f4f6"
          />
        </g>

        <!-- axes -->
        <line :x1="ML" :y1="MT" :x2="ML" :y2="MT+PH" stroke="#9ca3af" />
        <line :x1="ML" :y1="MT+PH" :x2="ML+PW" :y2="MT+PH" stroke="#9ca3af" />

        <!-- y ticks + labels -->
        <g v-for="t in yTicks" :key="'y'+t.v">
          <line
            :x1="ML-4" :x2="ML"
            :y1="yScale(t.v)" :y2="yScale(t.v)"
            stroke="#6b7280"
          />
          <text
            :x="ML-8"
            :y="yScale(t.v)+4"
            text-anchor="end"
            font-size="12"
            fill="#374151"
          >{{ t.label }}</text>
        </g>

        <!-- x ticks + labels -->
        <g v-for="t in xTicks" :key="'x'+t.v">
          <line
            :x1="xScale(t.v)" :x2="xScale(t.v)"
            :y1="MT+PH" :y2="MT+PH+4"
            stroke="#6b7280"
          />
          <text
            :x="xScale(t.v)"
            :y="MT+PH+18"
            text-anchor="middle"
            font-size="12"
            fill="#374151"
          >{{ t.label }}</text>
        </g>

        <!-- y axis label -->
        <text
          :x="14"
          :y="MT + PH/2"
          font-size="12"
          fill="#374151"
          text-anchor="middle"
          :transform="`rotate(-90 14 ${MT + PH/2})`"
        >{{ yLabel }}</text>

        <!-- x axis label -->
        <text
          :x="ML + PW/2"
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

      <!-- legend on the right -->
      <div class="legend">
        <div v-for="s in series" :key="'leg'+s.name" class="leg-item">
          <span class="swatch" :style="{ background: s.color }"></span>
          <span class="leg-text">{{ s.name }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  title: { type: String, default: "" },
  xLabel: { type: String, default: "Время (сек)" },
  yLabel: { type: String, default: "Количество" },

  xValues: { type: Array, default: () => [] },

  series: { type: Array, default: () => [] },

  yMax: { type: Number, default: null }
});

const W = 980;
const H = 260;
const ML = 56;  // left margin
const MR = 10;  // right margin inside svg
const MT = 14;  // top
const MB = 44;  // bottom for x-label

const PW = W - ML - MR;
const PH = H - MT - MB;

function toNum(x) {
  const v = Number(x);
  return Number.isFinite(v) ? v : 0;
}

const xMin = computed(() => {
  if (!props.xValues.length) return 0;
  return Math.min(...props.xValues.map(toNum));
});
const xMax = computed(() => {
  if (!props.xValues.length) return 1;
  return Math.max(...props.xValues.map(toNum));
});

const yMaxAuto = computed(() => {
  let m = 0;
  for (const s of props.series) {
    for (const v of (s.values || [])) m = Math.max(m, toNum(v));
  }
  return Math.max(1, m);
});

const yMax = computed(() => {
  if (props.yMax != null && Number.isFinite(Number(props.yMax))) {
    return Math.max(1e-6, Number(props.yMax));
  }
  return yMaxAuto.value;
});

function xScale(t) {
  const xmin = xMin.value;
  const xmax = xMax.value;
  const denom = Math.max(1e-6, xmax - xmin);
  const u = (toNum(t) - xmin) / denom;
  return ML + u * PW;
}

function yScale(v) {
  const u = toNum(v) / Math.max(1e-6, yMax.value);
  return MT + (PH - u * PH);
}

function pathFor(values) {
  const xs = props.xValues || [];
  if (!values || values.length === 0 || xs.length === 0) return "";

  const n = Math.min(values.length, xs.length);
  let d = "";
  for (let i = 0; i < n; i++) {
    const x = xScale(xs[i]);
    const y = yScale(values[i]);
    d += (i === 0 ? `M ${x} ${y}` : ` L ${x} ${y}`);
  }
  return d;
}

function makeTicks(minV, maxV, count, decimals = 0) {
  const out = [];
  if (count <= 1) return [{ v: minV, label: String(minV) }];

  for (let i = 0; i < count; i++) {
    const v = minV + (i * (maxV - minV)) / (count - 1);
    out.push({ v, label: v.toFixed(decimals) });
  }
  return out;
}

const xTicks = computed(() => {
  const xmin = xMin.value;
  const xmax = xMax.value;
  // 5 тиков как у “обычного” графика
  return makeTicks(xmin, xmax, 5, 1);
});

const yTicks = computed(() => {
  // 4 тика по Y
  return makeTicks(0, yMax.value, 4, 0);
});
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
  width: 160px;
  padding-top: 6px;
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
  display: inline-block;
}
.leg-text {
  white-space: nowrap;
}
</style>