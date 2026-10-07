<script setup>
import EmptyState from '../components/EmptyState.vue'
</script>
<template>
  <div class="panel">
    <EmptyState
      title="This page is not in the workspace"
      message="The address may have changed. Head back to the overview or claims register."
      icon="folder"
      ><RouterLink to="/" class="button button-primary">Back to overview</RouterLink></EmptyState
    >
  </div>
</template>
