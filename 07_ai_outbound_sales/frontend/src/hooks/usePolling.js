import { useState, useEffect, useCallback, useRef } from 'react'
import { useApi } from './useApi'

export function usePolling(url, interval = 5000) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const { get } = useApi()
  const intervalRef = useRef(null)

  const fetchData = useCallback(async () => {
    try {
      const result = await get(url)
      setData(result)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [get, url])

  const refetch = useCallback(() => {
    setLoading(true)
    return fetchData()
  }, [fetchData])

  useEffect(() => {
    fetchData()
    intervalRef.current = setInterval(fetchData, interval)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [fetchData, interval])

  return { data, loading, error, refetch }
}
