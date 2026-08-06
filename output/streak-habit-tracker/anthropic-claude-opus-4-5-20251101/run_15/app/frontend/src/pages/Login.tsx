import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuth } from '../hooks/useAuth';
import { LoginRequestSchema, type LoginRequest } from '../types';
import { Button } from '../components/Button';
import { Input } from '../components/Input';
import { ApiError } from '../lib/api';

export function LoginPage() {
  const { login, isAuthenticated, sessionExpired, clearSessionExpired } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginRequest>({
    resolver: zodResolver(LoginRequestSchema),
  });

  useEffect(() => {
    if (isAuthenticated) {
      const next = searchParams.get('next') || '/';
      navigate(next, { replace: true });
    }
  }, [isAuthenticated, navigate, searchParams]);

  const onSubmit = async (data: LoginRequest) => {
    setError(null);
    setIsLoading(true);
    clearSessionExpired();

    try {
      await login(data.email, data.password);
      const next = searchParams.get('next') || '/';
      navigate(next, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('An unexpected error occurred');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-semibold text-primary">Ethara</h1>
          <p className="text-sm text-muted mt-1">Streak Habit Tracker</p>
        </div>

        <div className="bg-surface rounded-card border border-border p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900 mb-6">Sign in</h2>

          {sessionExpired && (
            <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
              Your session has expired. Please sign in again.
            </div>
          )}

          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-danger">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <Input
              label="Email"
              type="email"
              autoComplete="email"
              {...register('email')}
              error={errors.email?.message}
            />

            <Input
              label="Password"
              type="password"
              autoComplete="current-password"
              {...register('password')}
              error={errors.password?.message}
            />

            <Button type="submit" className="w-full" disabled={isLoading}>
              {isLoading ? 'Signing in...' : 'Sign in'}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
