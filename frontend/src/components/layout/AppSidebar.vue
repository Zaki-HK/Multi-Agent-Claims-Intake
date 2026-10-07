<script setup>
import { useRoute } from 'vue-router'
import AppIcon from '../AppIcon.vue'
defineProps({ open: Boolean })
defineEmits(['close'])
const route = useRoute()
const links = [
  { to: '/', label: 'Overview', icon: 'dashboard', names: ['dashboard'] },
  { to: '/claims', label: 'Claims', icon: 'file', names: ['claims', 'claim', 'submit'] },
  { to: '/reviews', label: 'Review queue', icon: 'review', names: ['reviews'] },
  { to: '/policies', label: 'Policies', icon: 'folder', names: ['policies'] },
  { to: '/analytics', label: 'Analytics', icon: 'chart', names: ['analytics'] },
]
</script>
<template>
  <button
    v-if="open"
    type="button"
    class="sidebar-backdrop"
    aria-label="Close navigation"
    @click="$emit('close')"
  />
  <aside id="workspace-navigation" class="sidebar" :class="{ 'is-open': open }">
    <RouterLink to="/" class="brand"
      ><span class="brand-mark"><AppIcon name="shield" :size="25" /></span>claimdesk<span
        class="brand-period"
        >.</span
      ></RouterLink
    >
    <div class="workspace-label">
      <span class="workspace-avatar">IA</span
      ><span>Insurance operations<small>Claims workspace</small></span>
    </div>
    <span class="nav-label">WORKSPACE</span>
    <nav aria-label="Main navigation">
      <RouterLink
        v-for="link in links"
        :key="link.to"
        :to="link.to"
        class="nav-link"
        :class="{ active: link.names.includes(route.name) }"
        ><AppIcon :name="link.icon" /><span>{{ link.label }}</span
        ><AppIcon v-if="link.names.includes(route.name)" name="right" :size="15"
      /></RouterLink>
    </nav>
    <RouterLink to="/claims/new" class="sidebar-submit"
      ><AppIcon name="plus" :size="18" /> New claim</RouterLink
    >
    <div class="sidebar-note">
      <AppIcon name="shield" :size="22" /><strong>Evidence first.<br />People in the loop.</strong>
      <p>A clearer path from first notice to a considered decision.</p>
    </div>
    <div class="sidebar-footer"><span class="small-dot" />Internal claims workspace</div>
  </aside>
</template>
