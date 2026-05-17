import { useCallback, useEffect, useRef, useState } from 'react';

export type PipelineState = 'LISTENING' | 'THINKING' | 'SPEAKING' | 'IDLE';

interface CallWSMessage {
  type: string;
  state?: PipelineState;
  [key: string]: unknown;
}

interface UseCallWebSocketOptions {
  url: string;
  authToken: string;
  autoConnect?: boolean;
  reconnectInterval?: number;
  maxRetries?: number;
}

interface UseCallWebSocketReturn {
  connected: boolean;
  pipelineState: PipelineState;
  sendAudio: (data: ArrayBuffer) => void;
  lastResponse: CallWSMessage | null;
  audioChunks: ArrayBuffer[];
  disconnect: () => void;
}

export function useCallWebSocket({
  url,
  authToken,
  autoConnect = true,
  reconnectInterval = 3000,
  maxRetries = 5,
}: UseCallWebSocketOptions): UseCallWebSocketReturn {
  const [connected, setConnected] = useState(false);
  const [pipelineState, setPipelineState] = useState<PipelineState>('IDLE');
  const [lastResponse, setLastResponse] = useState<CallWSMessage | null>(null);
  const [audioChunks, setAudioChunks] = useState<ArrayBuffer[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const authSentRef = useRef(false);
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
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;
      authSentRef.current = false;

      ws.onopen = () => {
        // First-message auth pattern
        ws.send(JSON.stringify({ type: 'auth', token: authToken }));
        authSentRef.current = true;
        setConnected(true);
        retriesRef.current = 0;
      };

      ws.onmessage = (event: MessageEvent) => {
        if (event.data instanceof ArrayBuffer) {
          // Binary audio frame from server
          setAudioChunks((prev) => [...prev, event.data as ArrayBuffer]);
          return;
        }

        try {
          const msg = JSON.parse(event.data as string) as CallWSMessage;
          if (msg.type === 'pipeline_state' && msg.state) {
            setPipelineState(msg.state);
          }
          setLastResponse(msg);
        } catch {
          // Ignore non-JSON text messages
        }
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        authSentRef.current = false;

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

  const sendAudio = useCallback((data: ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN && authSentRef.current) {
      wsRef.current.send(data);
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

  return { connected, pipelineState, sendAudio, lastResponse, audioChunks, disconnect };
}
