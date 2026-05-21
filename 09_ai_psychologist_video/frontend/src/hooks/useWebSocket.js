import { useState, useEffect, useRef, useCallback } from 'react';
import { getToken } from '../utils/api';

/**
 * Хук для WebSocket-соединения с сервером звонка.
 * Поддерживает бинарные аудио-данные и JSON-сообщения.
 * Реализует автоматическое переподключение с экспоненциальным backoff.
 */
export function useWebSocket(sessionId) {
  const [status, setStatus] = useState('disconnected'); // disconnected | connecting | connected | error
  const [lastMessage, setLastMessage] = useState(null);
  const [isConnected, setIsConnected] = useState(false);

  const wsRef = useRef(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef(null);
  const intentionalCloseRef = useRef(false);

  const MAX_RECONNECT_ATTEMPTS = 5;
  const BASE_DELAY = 1000;

  const connect = useCallback(() => {
    if (!sessionId) return;

    const token = getToken();
    if (!token) {
      setStatus('error');
      return;
    }

    // Определяем протокол (ws/wss) в зависимости от текущего протокола страницы
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/call/${sessionId}?token=${token}`;

    setStatus('connecting');
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      setStatus('connected');
      setIsConnected(true);
      reconnectAttemptRef.current = 0;
    };

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        // Бинарные аудио-данные от AI
        setLastMessage({ type: 'audio', data: event.data });
      } else {
        // JSON-сообщения (статусы, события)
        try {
          const parsed = JSON.parse(event.data);
          setLastMessage(parsed);
        } catch {
          setLastMessage({ type: 'raw', data: event.data });
        }
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;

      if (!intentionalCloseRef.current && reconnectAttemptRef.current < MAX_RECONNECT_ATTEMPTS) {
        // Экспоненциальный backoff для переподключения
        const delay = BASE_DELAY * Math.pow(2, reconnectAttemptRef.current);
        reconnectAttemptRef.current += 1;
        setStatus('disconnected');

        reconnectTimerRef.current = setTimeout(() => {
          connect();
        }, delay);
      } else {
        setStatus('disconnected');
      }
    };

    ws.onerror = () => {
      setStatus('error');
    };
  }, [sessionId]);

  // Отправка аудио-чанка (бинарные данные)
  const sendAudio = useCallback((blob) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(blob);
    }
  }, []);

  // Отправка управляющего сообщения (mute/unmute/end_call)
  const sendControl = useCallback((control) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(control));
    }
  }, []);

  useEffect(() => {
    intentionalCloseRef.current = false;
    connect();

    return () => {
      intentionalCloseRef.current = true;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { status, sendAudio, sendControl, lastMessage, isConnected };
}
