import { useEffect, useRef, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getAccessToken } from '../api/client';

interface PriceUpdateMessage {
  type: 'price_update';
  product_id: string;
  old_price: number;
  new_price: number;
  discount_percent: number;
}

function getWsUrl(token: string): string {
  const apiUrl = import.meta.env.VITE_API_URL || '/api';
  // Convert http(s) to ws(s), or use relative ws path
  let wsBase: string;
  if (apiUrl.startsWith('http')) {
    wsBase = apiUrl.replace(/^http/, 'ws');
  } else {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    wsBase = `${protocol}//${window.location.host}${apiUrl}`;
  }
  return `${wsBase}/ws/prices?token=${encodeURIComponent(token)}`;
}

export function useWebSocket() {
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelayRef = useRef(1000);
  const mountedRef = useRef(true);

  const handleMessage = useCallback(
    (event: MessageEvent) => {
      try {
        const data: PriceUpdateMessage = JSON.parse(event.data);
        if (data.type === 'price_update') {
          // Invalidate product-related queries to trigger refetch
          queryClient.invalidateQueries({ queryKey: ['products'] });
          queryClient.invalidateQueries({ queryKey: ['product', data.product_id] });
          queryClient.invalidateQueries({ queryKey: ['deals'] });
        }
      } catch {
        // Ignore non-JSON messages (e.g. "pong")
      }
    },
    [queryClient]
  );

  const connect = useCallback(async () => {
    if (!mountedRef.current) return;

    const token = await getAccessToken();
    if (!token) return;

    const url = getWsUrl(token);

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        // Reset backoff on successful connection
        reconnectDelayRef.current = 1000;
      };

      ws.onmessage = handleMessage;

      ws.onclose = () => {
        wsRef.current = null;
        if (mountedRef.current) {
          // Reconnect with exponential backoff
          const delay = reconnectDelayRef.current;
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectDelayRef.current = Math.min(delay * 2, 30000);
            connect();
          }, delay);
        }
      };

      ws.onerror = () => {
        // Let onclose handle reconnection
        ws.close();
      };
    } catch {
      // Schedule reconnect on connection failure
      if (mountedRef.current) {
        const delay = reconnectDelayRef.current;
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectDelayRef.current = Math.min(delay * 2, 30000);
          connect();
        }, delay);
      }
    }
  }, [handleMessage]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);
}
