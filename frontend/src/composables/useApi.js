const root = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.claimId = detail?.claim_id || null
  }
}

function describe(detail) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail))
    return detail.map((item) => item.loc.slice(1).join(' ') + ': ' + item.msg).join('; ')
  return detail?.message || 'The request could not be completed. Please try again.'
}

export async function api(path, { query, body, timeout = 180000, signal, ...options } = {}) {
  const url = new URL(root + path, window.location.origin)
  for (const [key, value] of Object.entries(query || {})) {
    if (value !== '' && value !== null && value !== undefined) url.searchParams.set(key, value)
  }
  const controller = new AbortController()
  const abort = () => controller.abort()
  signal?.addEventListener('abort', abort, { once: true })
  if (signal?.aborted) abort()
  const timer = setTimeout(abort, timeout)
  const headers = { Accept: 'application/json', ...options.headers }
  if (body !== undefined && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(body)
  }
  try {
    const response = await fetch(url, { ...options, body, headers, signal: controller.signal })
    const payload = await response.json().catch(() => null)
    if (!response.ok)
      throw new ApiError(describe(payload?.detail), response.status, payload?.detail)
    return payload
  } catch (error) {
    if (error instanceof ApiError || signal?.aborted) throw error
    if (error.name === 'AbortError')
      throw new ApiError(
        'The request timed out. Refresh to check whether it completed before submitting again.',
        0,
        null,
      )
    throw new ApiError(
      'Could not reach the claims service. Check your connection and try again.',
      0,
      null,
    )
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', abort)
  }
}

// The backend returns evidence URLs rooted at /api/v1, including when accessed cross-origin.
export function evidenceUrl(path) {
  const base = new URL(root, window.location.origin)
  const suffix = path.startsWith('/api/v1/') ? path.slice('/api/v1'.length) : path
  return base.origin + base.pathname.replace(/\/$/, '') + suffix
}
