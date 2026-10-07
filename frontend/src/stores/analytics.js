import { defineStore } from 'pinia'
import { api } from '../composables/useApi'

export const useAnalyticsStore = defineStore('analytics', {
  state: () => ({ summary: null, trends: null, loading: false, error: '', serial: 0 }),
  actions: {
    async fetch(days = 30, signal) {
      const serial = ++this.serial
      this.loading = true
      this.error = ''
      try {
        const [summary, trends] = await Promise.all([
          api('/analytics/summary', { signal }),
          api('/analytics/trends', { query: { days }, signal }),
        ])
        if (serial === this.serial) {
          this.summary = summary
          this.trends = trends
        }
      } catch (error) {
        if (serial === this.serial && !signal?.aborted) this.error = error.message
      } finally {
        if (serial === this.serial) this.loading = false
      }
    },
  },
})
