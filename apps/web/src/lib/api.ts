import { QueryClient } from '@tanstack/react-query'

const BASE = 'http://127.0.0.1:8000'

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export const api = {
  async get<T>(path: string): Promise<T> {
    const response = await fetch(`${BASE}${path}`)
    let body: any
    try {
      body = await response.json()
    } catch {
      body = { detail: response.statusText }
    }
    if (!response.ok) {
      throw new ApiError(response.status, body?.detail || body?.message || `Request failed (${response.status})`)
    }
    return body
  },

  async post<T>(path: string, payload: unknown = {}): Promise<T> {
    const response = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    let result: any
    try {
      result = await response.json()
    } catch {
      result = { detail: response.statusText }
    }
    if (!response.ok) {
      throw new ApiError(response.status, result?.detail || result?.message || `Request failed (${response.status})`)
    }
    return result
  },

  async del<T = void>(path: string): Promise<T> {
    const response = await fetch(`${BASE}${path}`, { method: 'DELETE' })
    let result: any
    try {
      result = await response.json()
    } catch {
      result = undefined
    }
    if (!response.ok) {
      throw new ApiError(response.status, result?.detail || `Delete failed (${response.status})`)
    }
    return result
  },
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 3000,
    },
  },
})
