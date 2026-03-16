import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { apiFetch, apiUrl } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setTokenState] = useState(() => sessionStorage.getItem('clm_token'))
  const [user, setUser] = useState(() => {
    try {
      const u = sessionStorage.getItem('clm_user')
      return u ? JSON.parse(u) : null
    } catch {
      return null
    }
  })
  const [loading, setLoading] = useState(true)

  const setToken = useCallback((t) => {
    if (t) {
      sessionStorage.setItem('clm_token', t)
      setTokenState(t)
    } else {
      sessionStorage.removeItem('clm_token')
      sessionStorage.removeItem('clm_user')
      setTokenState(null)
      setUser(null)
    }
  }, [])

  const fetchMe = useCallback(async () => {
    if (!token) return
    try {
      const res = await apiFetch('/auth/me')
      const data = await res.json()
      setUser(data)
      sessionStorage.setItem('clm_user', JSON.stringify(data))
    } catch {
      setToken(null)
    }
  }, [token, setToken])

  useEffect(() => {
    if (!token) {
      setLoading(false)
      return
    }
    fetchMe().finally(() => setLoading(false))
  }, [token, fetchMe])

  const login = useCallback(async (email, password) => {
    const res = await fetch(apiUrl('/auth/login'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Login failed')
    }
    const data = await res.json()
    setToken(data.access_token)
    setUser({
      user_id: data.user_id,
      email: data.email,
      role: data.role,
      must_change_password: data.must_change_password,
    })
    sessionStorage.setItem('clm_user', JSON.stringify({
      user_id: data.user_id,
      email: data.email,
      role: data.role,
      must_change_password: data.must_change_password,
    }))
    return data
  }, [setToken])

  const logout = useCallback(() => {
    setToken(null)
  }, [setToken])

  const changePassword = useCallback(async (currentPassword, newPassword) => {
    const res = await apiFetch('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Failed to change password')
    }
    await fetchMe()
  }, [fetchMe])

  const value = {
    token,
    user,
    loading,
    login,
    logout,
    changePassword,
    fetchMe,
    setToken,
    isAdmin: user?.role === 'admin',
    mustChangePassword: user?.must_change_password === true,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
