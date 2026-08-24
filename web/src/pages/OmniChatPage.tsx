import React, { useState, useMemo } from 'react';
import { useHermesEventStream } from '../hooks/useHermesEventStream';
import { useHermesOperator } from '../hooks/useHermesOperator';
import type { HermesEvent } from '../types/hermes';

export function OmniChatPage() {
  const [ownerId] = useState<string>('default_user');
  const [inputMessage, setInputMessage] = useState<string>('');
  const [isSending, setIsSending] = useState<boolean>(false);

  const { events, isConnected, lastHeartbeat, error: streamError } = useHermesEventStream({
    ownerId,
  });

  const { submitCommand, isSubmitting } = useHermesOperator({
    ownerId,
  });

  const textDeltas = useMemo(() => {
    return events
      .filter((e: HermesEvent) => e.event_type === 'text_delta')
      .map((e: HermesEvent) => (e.data.delta as string) || '')
      .join('');
  }, [events]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputMessage.trim() || isSending) return;

    setIsSending(true);
    try {
      await fetch('/api/turn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          principal_id: ownerId,
          channel: 'omni',
          text: inputMessage,
        }),
      });
      setInputMessage('');
    } catch (err) {
      console.error('Failed to submit turn:', err);
    } finally {
      setIsSending(false);
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

      <div className="flex-1 overflow-y-auto p-4 bg-gray-900/50 rounded border border-gray-800 space-y-2">
        {events.length === 0 ? (
          <div className="text-gray-500 italic text-center py-8">
            No events yet. Start conversation below.
          </div>
        ) : (
          <div>
            <div className="text-gray-200 whitespace-pre-wrap">{textDeltas}</div>
            <div className="mt-4 pt-2 border-t border-gray-800 text-xs text-gray-500">
              Total events recorded: {events.length}
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
