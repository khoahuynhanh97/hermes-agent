export type HermesEventType =
  | 'text_delta'
  | 'clarification_required'
  | 'tool_activity'
  | 'workflow_state'
  | 'approval_required'
  | 'cost_update'
  | 'artifact'
  | 'warning'
  | 'completed'
  | 'failed'
  | 'heartbeat';

export interface HermesEvent {
  cursor?: number;
  event_id: string;
  event_type: HermesEventType;
  principal_id: string;
  session_id: string;
  turn_id: string;
  sequence: number;
  data: Record<string, unknown>;
  workflow_id?: string | null;
  job_id?: string | null;
  approval_id?: string | null;
  occurred_at: string;
}

export interface HermesArtifactMetadata {
  artifact_id: string;
  owner_user_id: string;
  artifact_type: string;
  version: number;
  digest: string;
  delivery_ref: string;
  metadata: Record<string, unknown>;
}

export interface HermesOperatorCommand {
  command_type: 'approve' | 'reject' | 'retry' | 'cancel' | 'upload' | 'form_update';
  target_id: string;
  expected_version: number | null;
  payload?: Record<string, unknown>;
}

export interface HermesHealthState {
  status: 'ready' | 'not_ready' | 'ok' | 'error';
  ready?: boolean;
  live?: boolean;
  failure_code?: string | null;
  details?: Record<string, unknown>;
}
