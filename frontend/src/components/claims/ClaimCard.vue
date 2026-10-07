<script setup>
import { dateTime, percent } from '../../composables/useClaims'
import StatusBadge from '../StatusBadge.vue'
import AppIcon from '../AppIcon.vue'
defineProps({ claim: Object })
</script>
<template>
  <RouterLink :to="'/claims/' + claim.id" class="review-card"
    ><div class="review-card-header">
      <span class="mono">{{ claim.claim_number }}</span
      ><StatusBadge :value="claim.status" />
    </div>
    <h3>{{ claim.claimant_name || 'Claimant not provided' }}</h3>
    <p>
      {{ claim.policy_number || 'Policy not provided' }} ·
      {{ percent(claim.confidence_score) }} confidence
    </p>
    <div class="review-card-footer">
      <span>{{ dateTime(claim.created_at, true) }}</span
      ><span class="text-link">Open claim <AppIcon name="arrow" :size="15" /></span></div
  ></RouterLink>
</template>
