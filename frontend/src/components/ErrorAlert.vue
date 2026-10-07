<script setup>
import AppIcon from './AppIcon.vue'
defineProps({ message: String, retry: { type: Boolean, default: false } })
defineEmits(['retry'])
</script>
<template>
  <div v-if="message" class="alert alert-error" role="alert">
    <AppIcon name="alert" /><span>{{ message }}</span
    ><button
      v-if="retry"
      type="button"
      class="button button-small button-ghost"
      @click="$emit('retry')"
    >
      Try again
    </button>
  </div>
</template>
