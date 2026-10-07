<script setup>
import { computed } from 'vue'
import { statuses, number } from '../../composables/useClaims'
const props = defineProps({ counts: { type: Object, default: () => ({}) } })
const rows = computed(() =>
  statuses
    .map((status) => ({ ...status, count: props.counts[status.value] || 0 }))
    .filter((item) => item.count),
)
const total = computed(() => rows.value.reduce((sum, row) => sum + row.count, 0))
const gradient = computed(() => {
  if (!total.value) return '#edf1e7'
  let cursor = 0
  return (
    'conic-gradient(' +
    rows.value
      .map((row) => {
        const start = cursor
        cursor += (row.count / total.value) * 100
        return row.color + ' ' + start + '% ' + cursor + '%'
      })
      .join(', ') +
    ')'
  )
})
</script>
<template>
  <div class="donut-layout">
    <div class="donut" :style="{ background: gradient }" aria-hidden="true">
      <div class="donut-center">
        <strong>{{ number(total) }}</strong
        ><small>total claims</small>
      </div>
    </div>
    <ul class="donut-legend" aria-label="Claims by status">
      <li v-for="row in rows" :key="row.value">
        <span class="legend-dot" :style="{ background: row.color }" />{{ row.label
        }}<strong>{{ number(row.count) }}</strong>
      </li>
      <li v-if="!rows.length" class="muted">No claims yet</li>
    </ul>
  </div>
</template>
