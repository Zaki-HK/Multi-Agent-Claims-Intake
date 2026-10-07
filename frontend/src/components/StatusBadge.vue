<script setup>
import { statusLabel, humanize } from '../composables/useClaims'
defineProps({ value: String, priority: Boolean })
</script>
<template>
  <span class="badge" :class="value"
    ><span class="status-dot" />{{
      priority ? humanize(value?.toLowerCase()) : statusLabel(value)
    }}</span
  >
</template>
