import { useCallback, useEffect, useRef, useState } from 'react';

export type MessageType = 'BALANCE_UPDATE' | 'TERMINATE_CALL';

export interface WSMessage {
  event_type: MessageType;
  balance_after: number;
  amount: number;
  user_id: string;
  session_id: string;
  timestamp: string;
}

interface UseWebSocketOptions {
  url: string;
  authToken?: string;
  autoConnect?: boolean;
  reconnectInterval?: number;
  maxRetries?: number;
}

interface UseWebSocketReturn {
  connected: boolean;
  lastMessage: WSMessage | null;
  sendMessage: (data: unknown) => void;
  connect: () => void;
  disconnect: () => void;
}

export function useWebSocket({
  url,
  authToken,
  autoConnect = true,
  reconnectInterval = 3000,
  maxRetries = 5,
}: UseWebSocketOptions): UseWebSocketReturn {
  const [connected, setConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shouldReconnectRef = useRef(true);

  const cleanup = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    cleanup();

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        // First-message auth pattern: send auth token if provided
        if (authToken) {
          ws.send(JSON.stringify({ type: 'auth', token: authToken }));
        }
        setConnected(true);
        retriesRef.current = 0;
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data) as WSMessage;
          setLastMessage(data);
        } catch {
          // Ignore non-JSON messages
        }
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;

        if (shouldReconnectRef.current && retriesRef.current < maxRetries) {
          retriesRef.current += 1;
          reconnectTimerRef.current = setTimeout(() => {
            connect();
          }, reconnectInterval);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      // Connection failed, will retry via onclose
    }
  }, [url, authToken, maxRetries, reconnectInterval, cleanup]);

  const disconnect = useCallback(() => {
    shouldReconnectRef.current = false;
    cleanup();
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
  }, [cleanup]);

  const sendMessage = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  useEffect(() => {
    if (autoConnect) {
      shouldReconnectRef.current = true;
      connect();
    }

    return () => {
      shouldReconnectRef.current = false;
      cleanup();
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [autoConnect, connect, cleanup]);

  return { connected, lastMessage, sendMessage, connect, disconnect };
}
