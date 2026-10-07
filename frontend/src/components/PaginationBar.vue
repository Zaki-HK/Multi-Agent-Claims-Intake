<script setup>
import AppIcon from './AppIcon.vue'
defineProps({ total: Number, offset: Number, limit: Number, disabled: Boolean })
defineEmits(['change'])
</script>
<template>
  <div class="pagination">
    <span>{{ total ? offset + 1 : 0 }}–{{ Math.min(offset + limit, total) }} of {{ total }}</span>
    <div class="button-group">
      <button
        type="button"
        class="button button-small button-ghost"
        :disabled="disabled || offset === 0"
        @click="$emit('change', Math.max(0, offset - limit))"
      >
        <AppIcon name="left" :size="16" /> Previous
      </button>
      <button
        type="button"
        class="button button-small button-ghost"
        :disabled="disabled || offset + limit >= total"
        @click="$emit('change', offset + limit)"
      >
        Next <AppIcon name="right" :size="16" />
      </button>
    </div>
  </div>
</template>
