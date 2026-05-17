import { useState, useEffect, useCallback } from 'react'

const TOKEN_KEY = 'ai_office_token'

/**
 * Auth hook for multi-tenant SaaS
 * Manages JWT token storage, login/register/logout, user state
 */
export function useAuth() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const getToken = useCallback(() => {
    return localStorage.getItem(TOKEN_KEY)
  }, [])

  const isAuthenticated = !!getToken()
  const isSuperAdmin = user?.is_super_admin || false

  const fetchUser = useCallback(async () => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) {
      setUser(null)
      setLoading(false)
      return
    }
    try {
      const response = await fetch('/api/auth/me', {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (!response.ok) {
        localStorage.removeItem(TOKEN_KEY)
        setUser(null)
        setLoading(false)
        return
      }
      const data = await response.json()
      setUser(data)
    } catch (err) {
      localStorage.removeItem(TOKEN_KEY)
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchUser()
  }, [fetchUser])

  const login = useCallback(async (email, password) => {
    setError(null)
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      })
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || 'Login failed')
      }
      const data = await response.json()
      localStorage.setItem(TOKEN_KEY, data.access_token)
      await fetchUser()
      return true
    } catch (err) {
      setError(err.message)
      return false
    }
  }, [fetchUser])

  const register = useCallback(async (email, password, companyName) => {
    setError(null)
    try {
      const response = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, company_name: companyName })
      })
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || 'Registration failed')
      }
      const data = await response.json()
      localStorage.setItem(TOKEN_KEY, data.access_token)
      await fetchUser()
      return true
    } catch (err) {
      setError(err.message)
      return false
    }
  }, [fetchUser])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setUser(null)
    setError(null)
  }, [])

  const refreshToken = useCallback(async () => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return false
    try {
      const response = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (!response.ok) {
        localStorage.removeItem(TOKEN_KEY)
        setUser(null)
        return false
      }
      const data = await response.json()
      localStorage.setItem(TOKEN_KEY, data.access_token)
      return true
    } catch (err) {
      localStorage.removeItem(TOKEN_KEY)
      setUser(null)
      return false
    }
  }, [])

  return {
    user,
    loading,
    error,
    isAuthenticated,
    isSuperAdmin,
    login,
    register,
    logout,
    refreshToken,
    getToken,
    setError
  }
}
