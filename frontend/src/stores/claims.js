import { defineStore } from 'pinia'
import { api } from '../composables/useApi'

export const useClaimsStore = defineStore('claims', {
  state: () => ({
    items: [],
    total: 0,
    detail: null,
    timeline: [],
    history: [],
    loading: false,
    error: '',
    serial: 0,
  }),
  actions: {
    async fetchList(query, signal) {
      const serial = ++this.serial
      this.loading = true
      this.error = ''
      try {
        const data = await api('/claims', { query, signal })
        if (serial === this.serial) {
          this.items = data.items
          this.total = data.total
        }
      } catch (error) {
        if (serial === this.serial && !signal?.aborted) this.error = error.message
      } finally {
        if (serial === this.serial) this.loading = false
      }
    },
    async fetchDetail(id, signal) {
      const serial = ++this.serial
      this.loading = true
      this.error = ''
      try {
        const [detail, timeline, history] = await Promise.all([
          api('/claims/' + id, { signal }),
          api('/claims/' + id + '/timeline', { signal }),
          api('/reviews/' + id + '/history', { signal }),
        ])
        if (serial === this.serial) {
          this.detail = detail
          this.timeline = timeline
          this.history = history
        }
      } catch (error) {
        if (serial === this.serial && !signal?.aborted) this.error = error.message
      } finally {
        if (serial === this.serial) this.loading = false
      }
    },
    submit(description, files) {
      const body = new FormData()
      body.append('description', description)
      files.forEach((file) => body.append('images', file))
      return api('/claims/fnol', { method: 'POST', body })
    },
    retry(id) {
      return api('/claims/' + id + '/retry', { method: 'POST' })
    },
  },
})
