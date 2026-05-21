import { useState, useEffect, useRef } from 'react'

const TOKEN_KEY = 'ai_office_token'

/**
 * Кастомный хук для polling данных с API
 * @param {string} endpoint - путь API (без /api/ префикса)
 * @param {number} interval - интервал опроса в мс (по умолчанию 3000)
 * @param {boolean} paused - приостановить polling (по умолчанию false)
 * @returns {{ data: any, loading: boolean, error: string|null }}
 */
export function useApi(endpoint, interval = 3000, paused = false) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const intervalRef = useRef(null)

  useEffect(() => {
    let isMounted = true

    const fetchData = async () => {
      try {
        const token = localStorage.getItem(TOKEN_KEY)
        const headers = {}
        if (token) {
          headers['Authorization'] = `Bearer ${token}`
        }
        const response = await fetch(`/api/${endpoint}`, { headers })
        if (response.status === 401) {
          localStorage.removeItem(TOKEN_KEY)
          if (isMounted) {
            setError('Unauthorized')
            setLoading(false)
          }
          return
        }
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        const json = await response.json()
        if (isMounted) {
          setData(json)
          setError(null)
          setLoading(false)
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message)
          setLoading(false)
        }
      }
    }

    // Первый запрос сразу (только если не paused или ещё нет данных)
    if (!paused || data === null) {
      fetchData()
    }

    // Polling с интервалом (только если не paused)
    if (!paused) {
      intervalRef.current = setInterval(fetchData, interval)
    }

    return () => {
      isMounted = false
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [endpoint, interval, paused])

  return { data, loading, error }
}
