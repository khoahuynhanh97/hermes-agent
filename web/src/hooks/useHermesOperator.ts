import { useState, useCallback } from 'react';
import type { HermesOperatorCommand } from '../types/hermes';

export interface UseHermesOperatorOptions {
  ownerId: string;
  authToken?: string;
  endpoint?: string;
}

export function useHermesOperator({
  ownerId,
  authToken = '',
  endpoint = '/api/operator/command',
}: UseHermesOperatorOptions) {
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [lastCommandId, setLastCommandId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submitCommand = useCallback(
    async (command: HermesOperatorCommand) => {
      setIsSubmitting(true);
      setError(null);

      try {
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${authToken}`,
          },
          body: JSON.stringify({
            auth_token: authToken,
            owner_id: ownerId,
            command_type: command.command_type,
            target_id: command.target_id,
            expected_version: command.expected_version,
            payload: command.payload || {},
          }),
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          throw new Error(errData.message || `Command failed with status ${response.status}`);
        }

        const data = await response.json();
        setLastCommandId(data.command_id || null);
        return data;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        throw err;
      } finally {
        setIsSubmitting(false);
      }
    },
    [ownerId, authToken, endpoint]
  );

  return {
    submitCommand,
    isSubmitting,
    lastCommandId,
    error,
  };
}
