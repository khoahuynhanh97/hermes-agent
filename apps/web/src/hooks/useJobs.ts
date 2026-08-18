import { useEffect, useState, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { JobItem, JobStatusType } from '../types/jobs'

const TERMINAL_STATES = new Set<string>([
  'succeeded',
  'completed',
  'failed',
  'cancelled',
  'timed_out',
  'error',
])

export function useJobPoller(jobId: string | null, onCompleted?: () => void) {
  const queryClient = useQueryClient()
  const [job, setJob] = useState<JobItem | null>(null)
  const [isPolling, setIsPolling] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Track terminal callback execution so it triggers exactly once
  const hasTriggeredTerminalRef = useRef<boolean>(false)
  const networkErrorCountRef = useRef<number>(0)
  const onCompletedRef = useRef(onCompleted)
  onCompletedRef.current = onCompleted

  useEffect(() => {
    hasTriggeredTerminalRef.current = false
    networkErrorCountRef.current = 0
    setError(null)

    if (!jobId) {
      setJob(null)
      setIsPolling(false)
      return
    }

    let isMounted = true
    let timerId: number | null = null
    setIsPolling(true)

    const poll = async () => {
      if (!isMounted || hasTriggeredTerminalRef.current) return

      try {
        const res = await api.get<{ id: string; task_name: string; status: string }>(
          `/api/jobs/${encodeURIComponent(jobId)}`
        )
        if (!isMounted) return

        networkErrorCountRef.current = 0
        const rawStatus = res.status?.toLowerCase() || 'unknown'
        const status = rawStatus as JobStatusType

        const currentJobItem: JobItem = {
          id: res.id,
          task_name: res.task_name,
          status,
        }
        setJob(currentJobItem)

        if (TERMINAL_STATES.has(rawStatus)) {
          setIsPolling(false)
          if (timerId) window.clearInterval(timerId)

          if (!hasTriggeredTerminalRef.current) {
            hasTriggeredTerminalRef.current = true
            queryClient.invalidateQueries({ queryKey: ['vf-projects'] })
            queryClient.invalidateQueries({ queryKey: ['vf-project'] })

            if (rawStatus === 'completed' || rawStatus === 'succeeded') {
              onCompletedRef.current?.()
            } else {
              setError(`Job ${res.id} terminated with status '${rawStatus}'.`)
            }
          }
        }
      } catch (err: any) {
        if (!isMounted) return
        networkErrorCountRef.current += 1

        if (networkErrorCountRef.current >= 5) {
          setIsPolling(false)
          if (timerId) window.clearInterval(timerId)

          const msg = err.message || 'Job polling network connection failed'
          setError(msg)
          setJob((prev) => (prev ? { ...prev, status: 'failed', error_message: msg } : null))
        }
      }
    }

    poll()
    timerId = window.setInterval(poll, 1500)

    return () => {
      isMounted = false
      if (timerId) window.clearInterval(timerId)
      setIsPolling(false)
    }
  }, [jobId, queryClient])

  return { job, isPolling, error }
}
