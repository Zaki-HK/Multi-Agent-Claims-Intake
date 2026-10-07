<script setup>
import { dateTime, percent } from '../../composables/useClaims'
import StatusBadge from '../StatusBadge.vue'
import AppIcon from '../AppIcon.vue'
defineProps({ claim: Object })
</script>
<template>
  <RouterLink
    :to="{ name: 'claim', params: { id: claim.id }, query: { tab: 'review' } }"
    class="review-card"
    ><div class="review-card-header">
      <span class="mono">{{ claim.claim_number }}</span
      ><StatusBadge :value="claim.priority || 'MEDIUM'" priority />
    </div>
    <h3>{{ claim.claimant_name || 'Claimant not provided' }}</h3>
    <p>
      {{
        claim.summary ||
        claim.incident_description ||
        'Open the assessment to inspect the reported incident.'
      }}
    </p>
    <ul>
      <li v-for="reason in claim.review_reasons" :key="reason">{{ reason }}</li>
    </ul>
    <div class="review-card-footer">
      <span
        >{{ percent(claim.confidence_score) }} confidence ·
        {{ dateTime(claim.created_at, true) }}</span
      ><span class="text-link">Review claim <AppIcon name="arrow" :size="15" /></span></div
  ></RouterLink>
</template>
