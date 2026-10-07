import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('../views/DashboardView.vue'),
      meta: { title: 'Overview', description: 'Your claims operation, at a glance.' },
    },
    {
      path: '/claims',
      name: 'claims',
      component: () => import('../views/ClaimsListView.vue'),
      meta: { title: 'Claims', description: 'Every submission. One place to follow its progress.' },
    },
    {
      path: '/claims/new',
      name: 'submit',
      component: () => import('../views/ClaimSubmitView.vue'),
      meta: { title: 'New claim', description: 'Start with the story. Add the evidence.' },
    },
    {
      path: '/claims/:id',
      name: 'claim',
      component: () => import('../views/ClaimDetailView.vue'),
      meta: {
        title: 'Claim workspace',
        description: 'Follow the evidence from intake to decision.',
      },
    },
    {
      path: '/policies',
      name: 'policies',
      component: () => import('../views/PoliciesView.vue'),
      meta: {
        title: 'Policies',
        description: 'The reference library behind every coverage assessment.',
      },
    },
    {
      path: '/reviews',
      name: 'reviews',
      component: () => import('../views/ReviewQueueView.vue'),
      meta: { title: 'Review queue', description: 'Your judgment, where it matters.' },
    },
    {
      path: '/analytics',
      name: 'analytics',
      component: () => import('../views/AnalyticsView.vue'),
      meta: {
        title: 'Analytics',
        description: 'Understand volume, decisions, and time to completion.',
      },
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('../views/NotFoundView.vue'),
      meta: { title: 'Page not found', description: 'Find your way back to the workspace.' },
    },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
router.afterEach((to) => {
  document.title = to.meta.title + ' · Claimdesk'
})
export default router
