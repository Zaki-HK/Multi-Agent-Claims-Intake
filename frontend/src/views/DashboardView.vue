<script setup>
import { computed } from 'vue'
import { useAnalyticsStore } from '../stores/analytics'
import { usePolling, number, dateTime, humanize } from '../composables/useClaims'
import AppIcon from '../components/AppIcon.vue'
import StatusBadge from '../components/StatusBadge.vue'
import ErrorAlert from '../components/ErrorAlert.vue'
import EmptyState from '../components/EmptyState.vue'
import ClaimsByStatus from '../components/charts/ClaimsByStatus.vue'
import TrendChart from '../components/charts/TrendChart.vue'
const store = useAnalyticsStore()
const { refresh } = usePolling((signal) => store.fetch(30, signal), { interval: 20000 })
const metrics = computed(() => [
  {
    label: 'Total claims',
    value: store.summary?.total_claims,
    icon: 'file',
    caption: 'All submitted claims',
  },
  {
    label: 'Awaiting review',
    value: store.summary?.under_review,
    icon: 'review',
    caption: 'Ready for your judgment',
  },
  {
    label: 'Auto-approved',
    value: store.summary?.auto_approved,
    icon: 'success',
    caption: 'Passed all approval criteria',
  },
  {
    label: 'Fraud flags',
    value: store.summary?.fraud_flagged,
    icon: 'shield',
    caption: 'Above the screening threshold',
  },
])
</script>
<template>
  <div class="page-heading">
    <div>
      <span class="eyebrow">CLAIMS OPERATIONS</span>
      <h1>A clear view of your day.</h1>
      <p>Follow your claims, focus your attention, and keep things moving.</p>
    </div>
    <RouterLink to="/claims/new" class="button button-primary"
      ><AppIcon name="plus" :size="17" />New claim</RouterLink
    >
  </div>
  <ErrorAlert :message="store.error" retry @retry="refresh" />
  <div v-if="store.summary" class="welcome-banner">
    <div>
      <h2>
        {{
          store.summary.under_review
            ? store.summary.under_review + ' claims need a closer look.'
            : 'Your workspace is ready.'
        }}
      </h2>
      <p>
        {{
          store.summary.under_review
            ? 'Review the evidence and record a considered decision.'
            : 'Submit a first notice of loss or explore your policy library.'
        }}
      </p>
    </div>
    <RouterLink
      :to="store.summary.under_review ? '/reviews' : '/policies'"
      class="button button-secondary"
      >{{ store.summary.under_review ? 'Open review queue' : 'View policies'
      }}<AppIcon name="arrow" :size="16"
    /></RouterLink>
  </div>
  <div class="stats-grid">
    <div v-for="metric in metrics" :key="metric.label" class="stat-card">
      <div class="stat-card-top">
        <span>{{ metric.label }}</span
        ><span class="stat-icon"><AppIcon :name="metric.icon" :size="18" /></span>
      </div>
      <strong class="stat-number">{{ number(metric.value) }}</strong
      ><span class="stat-foot">{{ metric.caption }}</span>
    </div>
  </div>
  <div v-if="!store.summary && store.loading" class="panel loading-state" role="status">
    <AppIcon name="loader" class="spin" />Loading your workspace…
  </div>
  <div v-if="store.summary" class="dashboard-grid">
    <div class="stack">
      <div class="panel">
        <div class="section-heading">
          <div>
            <h2>Claim activity</h2>
            <p>Submissions and decisions over the last {{ store.trends?.days || 30 }} days · UTC</p>
          </div>
          <RouterLink to="/analytics" class="text-link"
            >Analytics<AppIcon name="external" :size="14"
          /></RouterLink>
        </div>
        <TrendChart :points="store.trends?.points || []" />
      </div>
      <div class="panel">
        <div class="section-heading">
          <h2>Recent claims</h2>
          <RouterLink to="/claims" class="text-link"
            >View all<AppIcon name="arrow" :size="14"
          /></RouterLink>
        </div>
        <div v-if="store.summary.recent_claims.length" class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Claim / claimant</th>
                <th>Submitted</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="claim in store.summary.recent_claims" :key="claim.id">
                <td>
                  <RouterLink :to="'/claims/' + claim.id" class="claim-link mono">{{
                    claim.claim_number
                  }}</RouterLink
                  ><span class="table-subtitle">{{
                    claim.claimant_name || 'Claimant not provided'
                  }}</span>
                </td>
                <td class="muted">{{ dateTime(claim.created_at, true) }}</td>
                <td><StatusBadge :value="claim.status" /></td>
              </tr>
            </tbody>
          </table>
        </div>
        <EmptyState
          v-else
          title="Your first claim starts here"
          message="Submit an incident narrative and supporting images to begin."
          icon="file"
          ><RouterLink to="/claims/new" class="button button-secondary"
            >Create a claim</RouterLink
          ></EmptyState
        >
      </div>
    </div>
    <div class="stack">
      <div class="panel">
        <div class="section-heading"><h2>Claims by status</h2></div>
        <div class="panel-body"><ClaimsByStatus :counts="store.summary.by_status" /></div>
      </div>
      <div class="panel">
        <div class="section-heading">
          <h2>Recent activity</h2>
          <button
            type="button"
            class="icon-button"
            aria-label="Refresh dashboard"
            :disabled="store.loading"
            @click="refresh"
          >
            <AppIcon name="refresh" :size="16" />
          </button>
        </div>
        <div v-if="store.summary.recent_events.length" class="activity-list">
          <div v-for="event in store.summary.recent_events" :key="event.id" class="activity-item">
            <span class="activity-icon"
              ><AppIcon
                :name="event.event_type === 'claim_decided' ? 'success' : 'file'"
                :size="15"
            /></span>
            <div>
              <p>{{ humanize(event.event_type) }}</p>
              <RouterLink :to="'/claims/' + event.claim_id" class="text-link mono">{{
                event.claim_number
              }}</RouterLink
              ><br /><small>{{ dateTime(event.timestamp) }}</small>
            </div>
          </div>
        </div>
        <EmptyState
          v-else
          title="No activity yet"
          message="Claim updates will appear here."
          icon="clock"
        />
      </div>
    </div>
  </div>
</template>
