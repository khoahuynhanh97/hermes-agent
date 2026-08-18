export type JobStatusType =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'unknown'

export interface JobItem {
  id: string
  task_name: string
  status: JobStatusType
  payload?: Record<string, any>
  created_at?: string
  updated_at?: string
  error_message?: string
}
