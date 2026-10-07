<script setup>
import { ref } from 'vue'
import { useReviewsStore } from '../stores/reviews'
import { usePolling } from '../composables/useClaims'
import AppIcon from '../components/AppIcon.vue'
import ErrorAlert from '../components/ErrorAlert.vue'
import EmptyState from '../components/EmptyState.vue'
import PaginationBar from '../components/PaginationBar.vue'
import ReviewCard from '../components/reviews/ReviewCard.vue'
const store = useReviewsStore()
const offset = ref(0)
const limit = 12
const { refresh } = usePolling(
  async (signal) => {
    await store.fetchQueue({ limit, offset: offset.value }, signal)
    if (!store.error && offset.value && offset.value >= store.total) {
      offset.value = Math.max(0, Math.ceil(store.total / limit) - 1) * limit
      await store.fetchQueue({ limit, offset: offset.value }, signal)
    }
  },
  { interval: 15000 },
)
function page(value) {
  offset.value = value
  refresh()
}
</script>
<template>
  <div class="page-heading">
    <div>
      <span class="eyebrow">HUMAN REVIEW</span>
      <h1>A closer look makes a difference.</h1>
      <p>Review the full assessment before approving, rejecting, or overriding an outcome.</p>
    </div>
    <button
      type="button"
      class="button button-secondary"
      :disabled="store.loading"
      @click="refresh"
    >
      <AppIcon name="refresh" :size="16" :class="{ spin: store.loading }" />Refresh
    </button>
  </div>
  <ErrorAlert :message="store.error" retry @retry="refresh" />
  <div v-if="store.loaded" class="welcome-banner">
    <div>
      <h2>{{ store.total }} claims awaiting a decision</h2>
      <p>Ordered by submission time, with the earliest first.</p>
    </div>
    <AppIcon name="review" :size="36" class="welcome-icon" />
  </div>
  <div v-if="store.loading && !store.items.length" class="panel loading-state" role="status">
    <AppIcon name="loader" class="spin" />Loading review queue…
  </div>
  <div v-else-if="store.items.length" class="review-grid">
    <ReviewCard v-for="claim in store.items" :key="claim.id" :claim="claim" />
  </div>
  <div v-else-if="!store.error" class="panel">
    <EmptyState
      title="The review queue is clear"
      message="Claims that need your attention will appear here once assessment is complete."
      icon="success"
      ><RouterLink to="/claims" class="button button-secondary"
        >Browse all claims</RouterLink
      ></EmptyState
    >
  </div>
  <PaginationBar
    v-if="store.total"
    :total="store.total"
    :offset="offset"
    :limit="limit"
    :disabled="store.loading"
    @change="page"
  />
</template>
