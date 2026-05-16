import { useState, useEffect, useRef, useCallback } from 'react'

/**
 * WebSocket hook with auto-reconnect and event dispatching
 * @param {string} url - WebSocket URL (e.g., '/api/ws')
 * @param {object} handlers - Object mapping event types to handler functions
 * @returns {{ connected: boolean, error: string|null }}
 */
export function useWebSocket(url, handlers = {}) {
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState(null)
  const wsRef = useRef(null)
  const handlersRef = useRef(handlers)
  const reconnectAttempts = useRef(0)
  const maxReconnectAttempts = 5

  handlersRef.current = handlers

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}${url}`
    
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      setError(null)
      reconnectAttempts.current = 0
    }

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        const handler = handlersRef.current[message.event]
        if (handler) handler(message.data)
      } catch (e) {
        console.error('WS message parse error:', e)
      }
    }

    ws.onclose = () => {
      setConnected(false)
      // Auto-reconnect with exponential backoff
      if (reconnectAttempts.current < maxReconnectAttempts) {
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000)
        reconnectAttempts.current++
        setTimeout(connect, delay)
      } else {
        setError('Connection failed')
      }
    }

    ws.onerror = () => {
      setError('WebSocket error')
    }
  }, [url])

  useEffect(() => {
    connect()
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [connect])

  return { connected, error }
}
