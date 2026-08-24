import { useEffect, useRef, useState, useCallback } from 'react';
import type { HermesEvent } from '../types/hermes';

export interface UseHermesEventStreamOptions {
  ownerId: string;
  authToken?: string;
  initialCursor?: number;
  autoReconnect?: boolean;
  endpoint?: string;
}

export function useHermesEventStream({
  ownerId,
  authToken,
  initialCursor = 0,
  autoReconnect = true,
  endpoint = '/api/events',
}: UseHermesEventStreamOptions) {
  const [events, setEvents] = useState<HermesEvent[]>([]);
  const [cursor, setCursor] = useState<number>(initialCursor);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [lastHeartbeat, setLastHeartbeat] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cursorRef = useRef<number>(cursor);
  cursorRef.current = cursor;

  const connect = useCallback(() => {
    if (!ownerId) return;

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const url = new URL(endpoint, window.location.origin);
    url.searchParams.set('owner_id', ownerId);
    url.searchParams.set('after_seq', String(cursorRef.current));
    if (authToken) {
      url.searchParams.set('auth_token', authToken);
    }

    const es = new EventSource(url.toString());
    eventSourceRef.current = es;

    es.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    es.addEventListener('heartbeat', (e) => {
      try {
        const payload = JSON.parse(e.data);
        setLastHeartbeat(payload.timestamp || Date.now());
      } catch {
        setLastHeartbeat(Date.now());
      }
    });

    const eventTypes = [
      'text_delta',
      'clarification_required',
      'tool_activity',
      'workflow_state',
      'approval_required',
      'cost_update',
      'artifact',
      'warning',
      'completed',
      'failed',
    ];

    eventTypes.forEach((type) => {
      es.addEventListener(type, (e: MessageEvent) => {
        try {
          const parsedEvent: HermesEvent = JSON.parse(e.data);
          setEvents((prev) => [...prev, parsedEvent]);
          if (parsedEvent.sequence > cursorRef.current) {
            setCursor(parsedEvent.sequence);
          }
        } catch (err) {
          console.error('Failed to parse SSE event:', err);
        }
      });
    });

    es.onerror = () => {
      setIsConnected(false);
      setError('Event stream disconnected');
      es.close();
      if (autoReconnect) {
        reconnectTimerRef.current = setTimeout(() => {
          connect();
        }, 3000);
      }
    };
  }, [ownerId, authToken, endpoint, autoReconnect]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, [connect]);

  const clearEvents = useCallback(() => {
    setEvents([]);
  }, []);

  return {
    events,
    cursor,
    isConnected,
    lastHeartbeat,
    error,
    clearEvents,
    reconnect: connect,
  };
}
