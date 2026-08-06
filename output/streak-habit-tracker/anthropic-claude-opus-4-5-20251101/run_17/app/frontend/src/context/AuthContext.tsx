import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'

interface User {
  id: string
  email: string
}

interface AuthContextType {
  user: User | null
  token: string | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  handleSessionExpired: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    const storedToken = localStorage.getItem('token')
    const storedUser = localStorage.getItem('user')
    if (storedToken && storedUser) {
      setToken(storedToken)
      setUser(JSON.parse(storedUser))
    }
    setIsLoading(false)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Login failed' }))
      throw new Error(error.message || 'Login failed')
    }

    const data = await response.json()
    const newToken = data.access_token
    const newUser = data.user || { id: data.user_id || '', email }

    localStorage.setItem('token', newToken)
    localStorage.setItem('user', JSON.stringify(newUser))
    setToken(newToken)
    setUser(newUser)

    const params = new URLSearchParams(location.search)
    const next = params.get('next') || '/'
    navigate(next)
  }, [navigate, location.search])

  const logout = useCallback(() => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    setToken(null)
    setUser(null)
    navigate('/login')
  }, [navigate])

  const handleSessionExpired = useCallback(() => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    setToken(null)
    setUser(null)
    navigate(`/login?next=${encodeURIComponent(location.pathname)}&expired=1`)
  }, [navigate, location.pathname])

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, logout, handleSessionExpired }}>
      {children}
    </AuthContext.Provider>
  )
}
