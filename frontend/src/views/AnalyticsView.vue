<script setup>
import { computed, ref } from 'vue'
import { useAnalyticsStore } from '../stores/analytics'
import { usePolling, number, percent, duration } from '../composables/useClaims'
import AppIcon from '../components/AppIcon.vue'
import ErrorAlert from '../components/ErrorAlert.vue'
import TrendChart from '../components/charts/TrendChart.vue'
import ClaimsByStatus from '../components/charts/ClaimsByStatus.vue'
const store = useAnalyticsStore()
const days = ref(30)
const { refresh } = usePolling((signal) => store.fetch(days.value, signal), { interval: 30000 })
const submitted = computed(() =>
  store.trends?.points.reduce((sum, point) => sum + point.submitted, 0),
)
const decided = computed(() => store.trends?.points.reduce((sum, point) => sum + point.decided, 0))
</script>
<template>
  <div class="page-heading">
    <div>
      <span class="eyebrow">OPERATIONAL INSIGHTS</span>
      <h1>See the patterns. Find the focus.</h1>
      <p>Persisted claim activity, with clear definitions behind every metric.</p>
    </div>
    <div class="button-group">
      <label for="trend-period" class="sr-only">Trend period</label
      ><select id="trend-period" v-model.number="days" class="filter-input" @change="refresh">
        <option :value="7">Last 7 days</option>
        <option :value="30">Last 30 days</option>
        <option :value="90">Last 90 days</option></select
      ><button
        type="button"
        class="icon-button"
        :disabled="store.loading"
        aria-label="Refresh analytics"
        @click="refresh"
      >
        <AppIcon name="refresh" :size="18" />
      </button>
    </div>
  </div>
  <ErrorAlert :message="store.error" retry @retry="refresh" />
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-card-top">
        Submitted in period<span class="stat-icon"><AppIcon name="file" :size="18" /></span>
      </div>
      <strong class="stat-number">{{ number(submitted) }}</strong
      ><span class="stat-foot">By submission date · UTC</span>
    </div>
    <div class="stat-card">
      <div class="stat-card-top">
        Decided in period<span class="stat-icon"><AppIcon name="success" :size="18" /></span>
      </div>
      <strong class="stat-number">{{ number(decided) }}</strong
      ><span class="stat-foot">Final decisions by decision date · UTC</span>
    </div>
    <div class="stat-card">
      <div class="stat-card-top">
        Average time to decision<span class="stat-icon"><AppIcon name="clock" :size="18" /></span>
      </div>
      <strong class="stat-number">{{ duration(store.summary?.average_completion_seconds) }}</strong
      ><span class="stat-foot">All time · Includes human review wait</span>
    </div>
    <div class="stat-card">
      <div class="stat-card-top">
        Human override rate<span class="stat-icon"><AppIcon name="review" :size="18" /></span>
      </div>
      <strong class="stat-number">{{ percent(store.summary?.override_rate) }}</strong
      ><span class="stat-foot">All time · Overrides / accepted reviews</span>
    </div>
  </div>
  <div v-if="store.summary" class="stack">
    <div class="dashboard-grid">
      <div class="panel">
        <div class="section-heading">
          <div>
            <h2>Volume and decisions</h2>
            <p>{{ store.trends?.days }} days · Daily activity in UTC</p>
          </div>
        </div>
        <TrendChart :points="store.trends?.points || []" />
      </div>
      <div class="panel">
        <div class="section-heading"><h2>Current claim distribution</h2></div>
        <div class="panel-body"><ClaimsByStatus :counts="store.summary.by_status" /></div>
      </div>
    </div>
    <div class="metric-grid">
      <div class="stat-card">
        <span class="metric-title">Decisions by people</span
        ><strong class="metric-value">{{ number(store.summary.human_decisions) }}</strong
        ><span class="stat-foot">Accepted review decisions, including pending application</span>
      </div>
      <div class="stat-card">
        <span class="metric-title">Automatically approved</span
        ><strong class="metric-value">{{ number(store.summary.auto_approved) }}</strong
        ><span class="stat-foot">Approved claims with an automatic decision record</span>
      </div>
      <div class="stat-card">
        <span class="metric-title">Policy library</span
        ><strong class="metric-value"
          >{{ number(store.summary.indexed_policies) }} /
          {{ number(store.summary.total_policies) }}</strong
        ><span class="stat-foot">Policies with successfully ingested documents</span>
      </div>
    </div>
    <div class="panel">
      <div class="section-heading">
        <div>
          <h2>Daily performance</h2>
          <p>Time to decision is measured from original submission to recorded final outcome.</p>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Date (UTC)</th>
              <th>Submitted</th>
              <th>Decided</th>
              <th>Accepted reviews</th>
              <th>Overrides</th>
              <th>Average time to decision</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="point in store.trends?.points || []" :key="point.date">
              <td>{{ point.date }}</td>
              <td>{{ number(point.submitted) }}</td>
              <td>{{ number(point.decided) }}</td>
              <td>{{ number(point.human_decisions) }}</td>
              <td>{{ number(point.overrides) }}</td>
              <td>{{ duration(point.average_completion_seconds) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
  <div v-else-if="store.loading" class="panel loading-state" role="status">
    <AppIcon name="loader" class="spin" />Loading analytics…
  </div>
</template>
