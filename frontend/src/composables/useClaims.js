import { onBeforeUnmount, onMounted } from 'vue'

export const statuses = [
  { value: 'submitted', label: 'Submitted', color: '#94a3b8' },
  { value: 'intake', label: 'Intake', color: '#7c9db5' },
  { value: 'processing', label: 'Processing', color: '#559fba' },
  { value: 'triaged', label: 'Triaged', color: '#9582bb' },
  { value: 'under_review', label: 'Needs review', color: '#d7a34d' },
  { value: 'approved', label: 'Approved', color: '#5a987e' },
  { value: 'denied', label: 'Denied', color: '#c87c75' },
  { value: 'escalated', label: 'Escalated', color: '#bb7960' },
]
export const statusLabel = (value) =>
  statuses.find((item) => item.value === value)?.label || humanize(value)
export const humanize = (value) =>
  String(value || '')
    .replaceAll('_', ' ')
    .replace(/^./, (c) => c.toUpperCase())
export const number = (value) =>
  value === null || value === undefined
    ? '—'
    : new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value)
export const percent = (value) =>
  value === null || value === undefined ? '—' : Math.round(value * 100) + '%'
export function dateTime(value, short = false) {
  if (!value) return '—'
  // Persisted backend timestamps are UTC even where their ISO representation lacks Z.
  const normalized =
    /^\d{4}-\d{2}-\d{2}T/.test(value) && !/(Z|[+-]\d{2}:\d{2})$/.test(value) ? value + 'Z' : value
  const date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? value + 'T00:00:00' : normalized)
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        ...(short ? {} : { hour: '2-digit', minute: '2-digit' }),
      }).format(date)
}
export function duration(seconds) {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 60) return Math.round(seconds) + 's'
  if (seconds < 3600) return Math.round(seconds / 60) + 'm'
  if (seconds < 86400) return (seconds / 3600).toFixed(1) + 'h'
  return (seconds / 86400).toFixed(1) + 'd'
}

// Completion-based scheduling prevents overlapping requests. Cleanup also aborts in-flight reads.
export function usePolling(load, { interval = 10000, enabled = () => true } = {}) {
  const controller = new AbortController()
  let timer
  let running = false
  let disposed = false
  let queued = false
  async function refresh() {
    if (disposed) return
    if (running) {
      queued = true
      return
    }
    clearTimeout(timer)
    running = true
    try {
      await load(controller.signal)
    } catch (error) {
      if (error.name !== 'AbortError') console.error('Workspace refresh failed')
    } finally {
      running = false
      if (!disposed && queued) {
        queued = false
        queueMicrotask(refresh)
      } else if (!disposed) timer = setTimeout(tick, interval)
    }
  }
  function tick() {
    if (document.hidden || !enabled()) timer = setTimeout(tick, interval)
    else refresh()
  }
  function visible() {
    if (!document.hidden && enabled()) refresh()
  }
  onMounted(() => {
    document.addEventListener('visibilitychange', visible)
    refresh()
  })
  onBeforeUnmount(() => {
    disposed = true
    clearTimeout(timer)
    controller.abort()
    document.removeEventListener('visibilitychange', visible)
  })
  return { refresh }
}
