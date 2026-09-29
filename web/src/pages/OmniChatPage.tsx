import React, { useState, useMemo } from 'react';
import { useHermesEventStream } from '../hooks/useHermesEventStream';
import { useHermesOperator } from '../hooks/useHermesOperator';
import type { HermesEvent } from '../types/hermes';

export function OmniChatPage() {
  const [ownerId] = useState<string>(() => window.__HERMES_OWNER_ID__ ?? 'local-owner');
  const authToken = window.__HERMES_SESSION_TOKEN__ ?? '';
  const [inputMessage, setInputMessage] = useState<string>('');
  const [isSending, setIsSending] = useState<boolean>(false);

  const { events, isConnected, lastHeartbeat, error: streamError } = useHermesEventStream({
    ownerId,
    authToken,
  });

  const { submitCommand, isSubmitting, lastCommandId, error: operatorError } = useHermesOperator({
    ownerId,
    authToken,
  });

  const textDeltas = useMemo(() => {
    return events
      .filter((e: HermesEvent) => e.event_type === 'text_delta')
      .map((e: HermesEvent) => (e.data.text as string) || '')
      .join('');
  }, [events]);

  const pendingApprovals = useMemo(() => {
    return events.filter((e: HermesEvent) => e.event_type === 'approval_required');
  }, [events]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputMessage.trim() || isSending) return;

    setIsSending(true);
    try {
      const response = await fetch('/api/omni/turn', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({
          conversation_id: 'omni-web',
          message: inputMessage,
        }),
      });
      if (!response.ok) {
        throw new Error(`Turn failed with status ${response.status}`);
      }
      setInputMessage('');
    } catch (err) {
      console.error('Failed to submit turn:', err);
    } finally {
      setIsSending(false);
    }
  };

  const handleApprove = async (event: HermesEvent) => {
    // Use event.approval_id as the target — this is the ApprovalRequest ID the backend
    // resolves via ApprovalService.get_request(). Fall back to workflow_id if approval_id
    // is absent (backend also accepts workflow_id and resolves pending_approval_id from the
    // aggregate). Never use turn_id/event_id — those don't map to approval records.
    // Pass expected_version: null so the backend skips the stale-version guard (the UI
    // does not track workflow version; the backend enforces idempotency via approval_id).
    const targetId = event.approval_id ?? event.workflow_id;
    if (!targetId) {
      console.error('Approval event missing both approval_id and workflow_id — cannot approve', event);
      return;
    }
    try {
      await submitCommand({
        command_type: 'approve',
        target_id: targetId,
        expected_version: null,
        payload: { reason: 'Operator approved via Omni UI' },
      });
    } catch (err) {
      console.error('Approval failed:', err);
    }
  };

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto p-4 space-y-4">
      <header className="flex justify-between items-center pb-2 border-b border-gray-700">
        <h1 className="text-xl font-bold">Hermes Omni Unified Channel</h1>
        <div className="flex items-center space-x-2 text-sm">
          <span
            className={`w-3 h-3 rounded-full ${
              isConnected ? 'bg-green-500' : 'bg-red-500'
            }`}
          />
          <span>{isConnected ? 'Connected' : 'Disconnected'}</span>
          {lastHeartbeat && (
            <span className="text-gray-400 text-xs">
              (Heartbeat: {new Date(lastHeartbeat).toLocaleTimeString()})
            </span>
          )}
        </div>
      </header>

      {streamError && (
        <div className="p-3 bg-red-900/40 border border-red-500 rounded text-red-200 text-sm">
          Stream Error: {streamError}
        </div>
      )}

      {operatorError && (
        <div className="p-3 bg-red-900/40 border border-red-500 rounded text-red-200 text-sm">
          Operator Error: {operatorError}
        </div>
      )}

      {pendingApprovals.length > 0 && (
        <div className="p-3 bg-amber-950/40 border border-amber-500 rounded space-y-2">
          <div className="text-sm font-semibold text-amber-300">Pending Operator Approvals</div>
          {pendingApprovals.map((appr) => (
            <div key={appr.event_id} className="flex justify-between items-center text-xs text-amber-200">
              <span>
                Approval{appr.approval_id ? ` ${appr.approval_id}` : ''} for workflow{' '}
                {appr.workflow_id ?? appr.turn_id}
              </span>
              <button
                type="button"
                disabled={isSubmitting || (!appr.approval_id && !appr.workflow_id)}
                onClick={() => void handleApprove(appr)}
                className="px-3 py-1 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white rounded font-medium"
              >
                {isSubmitting ? 'Approving...' : 'Approve Action'}
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-4 bg-gray-900/50 rounded border border-gray-800 space-y-2">
        {events.length === 0 ? (
          <div className="text-gray-500 italic text-center py-8">
            No events yet. Start conversation below.
          </div>
        ) : (
          <div>
            <div className="text-gray-200 whitespace-pre-wrap">{textDeltas}</div>
            <div className="mt-4 pt-2 border-t border-gray-800 text-xs text-gray-500 flex justify-between">
              <span>Total events recorded: {events.length}</span>
              {lastCommandId && <span>Last Operator Command: {lastCommandId}</span>}
            </div>
          </div>
        )}
      </div>

      <form onSubmit={handleSend} className="flex space-x-2">
        <input
          type="text"
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          placeholder="Send a natural language instruction to Hermes..."
          className="flex-1 p-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
          disabled={isSending}
        />
        <button
          type="submit"
          disabled={isSending || !inputMessage.trim()}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded font-medium"
        >
          {isSending ? 'Sending...' : 'Send'}
        </button>
      </form>
    </div>
  );
}

export default OmniChatPage;
