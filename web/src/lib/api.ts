import { QueryClient } from '@tanstack/react-query'

const BASE = 'http://127.0.0.1:8000'

export const api = {
  get<T>(path: string): Promise<T> {
    return fetch(`${BASE}${path}`).then((r) => r.json())
  },
  post<T>(path: string, body: unknown): Promise<T> {
    return fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then((r) => r.json())
  },
  del(path: string): Promise<void> {
    return fetch(`${BASE}${path}`, { method: 'DELETE' }).then(() => undefined)
  },
}

export const queryClient = new QueryClient()