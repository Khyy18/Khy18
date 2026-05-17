import { useCallback } from 'react'
import { useAuth } from '../context/AuthContext'

export function useApi() {
  const { token, logout } = useAuth()

  const apiFetch = useCallback(async (url, options = {}) => {
    const headers = {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    }

    const res = await fetch(url, { ...options, headers })

    if (res.status === 401) {
      logout()
      throw new Error('Session expired')
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Request failed: ${res.status}`)
    }

    if (res.status === 204) return null
    return res.json()
  }, [token, logout])

  const get = useCallback((url) => apiFetch(url), [apiFetch])

  const post = useCallback((url, body) => apiFetch(url, {
    method: 'POST',
    body: JSON.stringify(body),
  }), [apiFetch])

  const put = useCallback((url, body) => apiFetch(url, {
    method: 'PUT',
    body: JSON.stringify(body),
  }), [apiFetch])

  const del = useCallback((url) => apiFetch(url, {
    method: 'DELETE',
  }), [apiFetch])

  return { get, post, put, del }
}
