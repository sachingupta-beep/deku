import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useAuth } from '../context/AuthContext'
import { LoginSchema, LoginInput } from '../types'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

export default function Login() {
  const { login } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [searchParams] = useSearchParams()
  const expired = searchParams.get('expired')

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginInput>({
    resolver: zodResolver(LoginSchema),
  })

  const onSubmit = async (data: LoginInput) => {
    setError(null)
    try {
      await login(data.email, data.password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    }
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-semibold text-gray-900">Ethara</h1>
          <p className="text-sm text-muted mt-1">Streak Habit Tracker</p>
        </div>

        <div className="bg-surface rounded-card border border-border p-6 shadow-sm">
          <h2 className="text-lg font-medium text-gray-900 mb-6">Sign in</h2>

          {expired && (
            <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded text-sm text-amber-800">
              Your session has expired. Please sign in again.
            </div>
          )}

          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-danger">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
                Email
              </label>
              <input
                id="email"
                type="email"
                {...register('email')}
                className="w-full px-3 py-2 border border-border rounded focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                placeholder="demo@ethara.ai"
              />
              {errors.email && (
                <p className="mt-1 text-sm text-danger">{errors.email.message}</p>
              )}
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
                Password
              </label>
              <input
                id="password"
                type="password"
                {...register('password')}
                className="w-full px-3 py-2 border border-border rounded focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              />
              {errors.password && (
                <p className="mt-1 text-sm text-danger">{errors.password.message}</p>
              )}
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-2.5 bg-primary text-white font-medium rounded hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? 'Signing in...' : 'Sign in'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
