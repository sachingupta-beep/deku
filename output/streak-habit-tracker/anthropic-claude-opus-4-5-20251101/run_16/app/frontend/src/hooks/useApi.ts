import { useAuth } from '../context/AuthContext'
import { useCallback } from 'react'

export function useApi() {
  const { token, handleSessionExpired } = useAuth()

  const apiFetch = useCallback(async <T>(
    url: string,
    options: RequestInit = {}
  ): Promise<T> => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    }

    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    const response = await fetch(url, {
      ...options,
      headers,
    })

    if (response.status === 401) {
      handleSessionExpired()
      throw new Error('Session expired')
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Request failed' }))
      throw new Error(error.message || `Request failed with status ${response.status}`)
    }

    if (response.status === 204) {
      return undefined as T
    }

    return response.json()
  }, [token, handleSessionExpired])

  return { apiFetch }
}
