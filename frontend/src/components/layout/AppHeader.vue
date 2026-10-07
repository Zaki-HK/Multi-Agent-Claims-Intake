<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '../AppIcon.vue'
defineProps({ navigationOpen: Boolean })
defineEmits(['toggle'])
const route = useRoute()
const router = useRouter()
const search = ref('')
function submit() {
  router.push({ name: 'claims', query: search.value.trim() ? { search: search.value.trim() } : {} })
  search.value = ''
}
</script>
<template>
  <header class="app-header">
    <div class="header-breadcrumb">
      <button
        type="button"
        class="icon-button mobile-menu"
        aria-label="Toggle navigation"
        aria-controls="workspace-navigation"
        :aria-expanded="navigationOpen"
        @click="$emit('toggle')"
      >
        <AppIcon name="menu" /></button
      ><span>Workspace</span><AppIcon name="right" :size="14" /><strong>{{
        route.meta.title
      }}</strong>
    </div>
    <form class="header-search" role="search" @submit.prevent="submit">
      <AppIcon name="search" :size="17" /><input
        v-model="search"
        aria-label="Search claims by claimant, claim, or policy number"
        placeholder="Search claims or policy numbers…"
        maxlength="255"
      /><span class="search-hint">↵</span>
    </form>
    <span class="header-avatar" title="Internal workspace">IA</span>
  </header>
</template>
