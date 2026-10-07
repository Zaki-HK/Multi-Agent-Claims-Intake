<script setup>
import AppIcon from './AppIcon.vue'
defineProps({ title: String, message: String, icon: { type: String, default: 'folder' } })
</script>
<template>
  <div class="empty-state">
    <span class="empty-icon"><AppIcon :name="icon" :size="28" /></span>
    <h3>{{ title }}</h3>
    <p>{{ message }}</p>
    <slot />
  </div>
</template>
