import { defineStore } from 'pinia'
import { api } from '../composables/useApi'

export const useReviewsStore = defineStore('reviews', {
  state: () => ({ items: [], total: 0, loading: false, loaded: false, error: '', serial: 0 }),
  actions: {
    async fetchQueue(query, signal) {
      const serial = ++this.serial
      this.loading = true
      this.error = ''
      try {
        const data = await api('/reviews/queue', { query, signal })
        if (serial === this.serial) {
          this.items = data.items
          this.total = data.total
          this.loaded = true
        }
      } catch (error) {
        if (serial === this.serial && !signal?.aborted) this.error = error.message
      } finally {
        if (serial === this.serial) this.loading = false
      }
    },
    decide(id, body) {
      return api('/reviews/' + id + '/decision', { method: 'POST', body })
    },
  },
})
