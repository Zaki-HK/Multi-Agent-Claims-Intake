<script setup>
import { computed } from 'vue'
const props = defineProps({ points: { type: Array, default: () => [] } })
const max = computed(() =>
  Math.max(4, ...props.points.flatMap((point) => [point.submitted, point.decided])),
)
const coordinate = (index, value) =>
  45 +
  (index / Math.max(1, props.points.length - 1)) * 570 +
  ',' +
  (180 - (value / max.value) * 150)
const line = (key) => props.points.map((point, index) => coordinate(index, point[key])).join(' ')
const labels = computed(() =>
  props.points.filter(
    (_, i) =>
      i === 0 ||
      i === props.points.length - 1 ||
      i % Math.max(1, Math.ceil(props.points.length / 6)) === 0,
  ),
)
function label(day) {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(day + 'T00:00:00Z'))
}
</script>
<template>
  <div class="chart-wrap">
    <div class="chart-legend">
      <span><i class="legend-dot" style="background: #739360" />Submitted</span
      ><span><i class="legend-dot" style="background: #c8a260" />Decided</span>
    </div>
    <svg
      viewBox="0 0 640 225"
      class="trend-chart"
      role="img"
      aria-label="Daily submitted and decided claims. Exact values are available in the accessible data table."
    >
      <g v-for="tick in [0, 1, 2, 3]" :key="tick">
        <line
          x1="45"
          x2="615"
          :y1="180 - tick * 50"
          :y2="180 - tick * 50"
          stroke="#edf1e7"
          stroke-dasharray="3 4"
        />
        <text x="33" :y="184 - tick * 50" text-anchor="end" fill="#9cab90" font-size="9">
          {{ Math.round((max * tick) / 3) }}
        </text>
      </g>
      <polyline
        v-if="points.length"
        :points="line('submitted')"
        fill="none"
        stroke="#739360"
        stroke-width="2.5"
        stroke-linejoin="round"
      />
      <polyline
        v-if="points.length"
        :points="line('decided')"
        fill="none"
        stroke="#c8a260"
        stroke-width="2"
        stroke-linejoin="round"
        stroke-dasharray="5 4"
      />
      <g v-for="(point, index) in points" :key="point.date">
        <circle
          :cx="45 + (index / Math.max(1, points.length - 1)) * 570"
          :cy="180 - (point.submitted / max) * 150"
          r="3"
          fill="#739360"
        >
          <title>
            {{ point.date }}: {{ point.submitted }} submitted, {{ point.decided }} decided
          </title>
        </circle>
      </g>
      <text
        v-for="point in labels"
        :key="point.date"
        :x="45 + (points.indexOf(point) / Math.max(1, points.length - 1)) * 570"
        y="207"
        text-anchor="middle"
        fill="#9cab90"
        font-size="9"
      >
        {{ label(point.date) }}
      </text>
    </svg>
    <details class="text-small muted">
      <summary>View daily values</summary>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Date (UTC)</th>
              <th>Submitted</th>
              <th>Decided</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="point in points" :key="point.date">
              <td>{{ point.date }}</td>
              <td>{{ point.submitted }}</td>
              <td>{{ point.decided }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
  </div>
</template>
