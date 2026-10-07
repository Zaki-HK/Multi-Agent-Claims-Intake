<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useClaimsStore } from '../stores/claims'
import { statuses, usePolling, dateTime, percent } from '../composables/useClaims'
import AppIcon from '../components/AppIcon.vue'
import StatusBadge from '../components/StatusBadge.vue'
import ErrorAlert from '../components/ErrorAlert.vue'
import EmptyState from '../components/EmptyState.vue'
import PaginationBar from '../components/PaginationBar.vue'
const route = useRoute()
const router = useRouter()
const store = useClaimsStore()
const search = ref(String(route.query.search || ''))
const status = ref(String(route.query.status || ''))
const from = ref(String(route.query.date_from || ''))
const to = ref(String(route.query.date_to || ''))
const limit = 20
const offset = computed(() =>
  Number.isFinite(Number(route.query.offset))
    ? Math.max(0, Math.trunc(Number(route.query.offset)))
    : 0,
)
const { refresh } = usePolling(
  (signal) => store.fetchList({ ...route.query, limit, offset: offset.value }, signal),
  { interval: 15000 },
)
function filter(nextOffset = 0) {
  router.push({
    name: 'claims',
    query: {
      ...(search.value.trim() ? { search: search.value.trim() } : {}),
      ...(status.value ? { status: status.value } : {}),
      ...(from.value ? { date_from: from.value } : {}),
      ...(to.value ? { date_to: to.value } : {}),
      ...(nextOffset ? { offset: nextOffset } : {}),
    },
  })
}
watch(
  () => route.fullPath,
  () => {
    search.value = String(route.query.search || '')
    status.value = String(route.query.status || '')
    from.value = String(route.query.date_from || '')
    to.value = String(route.query.date_to || '')
    store.fetchList({ ...route.query, limit, offset: offset.value })
  },
)
</script>
<template>
  <div class="page-heading">
    <div>
      <span class="eyebrow">CLAIMS REGISTER</span>
      <h1>Every claim, in view.</h1>
      <p>Search the register and follow each submission to its outcome.</p>
    </div>
    <RouterLink to="/claims/new" class="button button-primary"
      ><AppIcon name="plus" :size="17" />New claim</RouterLink
    >
  </div>
  <form class="filters" @submit.prevent="filter()">
    <div class="field search-field">
      <label for="claim-search">Find a claim</label
      ><input
        id="claim-search"
        v-model="search"
        maxlength="255"
        placeholder="Claim number, claimant, or policy number"
      />
    </div>
    <div class="field">
      <label for="status-filter">Status</label
      ><select id="status-filter" v-model="status">
        <option value="">All statuses</option>
        <option v-for="item in statuses" :key="item.value" :value="item.value">
          {{ item.label }}
        </option>
      </select>
    </div>
    <div class="field">
      <label for="date-from">From (UTC)</label
      ><input id="date-from" v-model="from" type="date" :max="to || undefined" />
    </div>
    <div class="field">
      <label for="date-to">To (UTC)</label
      ><input id="date-to" v-model="to" type="date" :min="from || undefined" />
    </div>
    <button type="submit" class="button button-secondary">
      <AppIcon name="search" :size="16" />Apply
    </button>
  </form>
  <ErrorAlert :message="store.error" retry @retry="refresh" />
  <div class="panel">
    <div class="section-heading">
      <h2>
        Claims <span class="muted text-small">/ {{ store.total }}</span>
      </h2>
      <button
        type="button"
        class="icon-button"
        :disabled="store.loading"
        aria-label="Refresh claims"
        @click="refresh"
      >
        <AppIcon name="refresh" :size="16" :class="{ spin: store.loading }" />
      </button>
    </div>
    <div v-if="store.loading && !store.items.length" class="loading-state" role="status">
      <AppIcon name="loader" class="spin" />Loading claims…
    </div>
    <div v-else-if="store.items.length" class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Claim number</th>
            <th>Claimant / policy</th>
            <th>Status</th>
            <th>Priority</th>
            <th>Confidence</th>
            <th>Submitted</th>
            <th><span class="sr-only">Open claim</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="claim in store.items" :key="claim.id">
            <td>
              <RouterLink :to="'/claims/' + claim.id" class="claim-link mono">{{
                claim.claim_number
              }}</RouterLink>
            </td>
            <td>
              {{ claim.claimant_name || 'Not provided'
              }}<span class="table-subtitle">{{
                claim.policy_number || 'Policy not provided'
              }}</span>
            </td>
            <td><StatusBadge :value="claim.status" /></td>
            <td>
              <StatusBadge v-if="claim.priority" :value="claim.priority" priority /><span
                v-else
                class="muted"
                >—</span
              >
            </td>
            <td>{{ percent(claim.confidence_score) }}</td>
            <td class="muted">{{ dateTime(claim.created_at, true) }}</td>
            <td>
              <RouterLink
                :to="'/claims/' + claim.id"
                class="icon-button"
                :aria-label="'Open ' + claim.claim_number"
                ><AppIcon name="external" :size="17"
              /></RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <EmptyState
      v-else-if="!store.error"
      title="No matching claims"
      message="Adjust your filters or submit the first claim."
      icon="file"
    />
    <PaginationBar
      :total="store.total"
      :offset="offset"
      :limit="limit"
      :disabled="store.loading"
      @change="filter"
    />
  </div>
</template>
