<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppSidebar from './AppSidebar.vue'
import AppHeader from './AppHeader.vue'
const route = useRoute()
const open = ref(false)
watch(
  () => route.fullPath,
  () => {
    open.value = false
  },
)
</script>
<template>
  <a class="skip-link" href="#main-content">Skip to content</a>
  <AppSidebar :open="open" @close="open = false" />
  <div class="app-main">
    <AppHeader :navigation-open="open" @toggle="open = !open" />
    <main id="main-content" tabindex="-1">
      <RouterView v-slot="{ Component }"
        ><component :is="Component" :key="route.name === 'claim' ? route.params.id : route.name"
      /></RouterView>
    </main>
    <footer class="app-footer">
      Claimdesk <span>Thoughtful decisions start with clear evidence.</span>
    </footer>
  </div>
</template>
