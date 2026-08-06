import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useApi } from '../hooks/useApi'
import { Dashboard as DashboardType, Habit, HABIT_COLORS } from '../types'
import { Link } from 'react-router-dom'

function getColorHex(color: string): string {
  return HABIT_COLORS.find(c => c.value === color)?.hex || '#4F46E5'
}

function getTodayISO(): string {
  return new Date().toISOString().split('T')[0]
}

export default function Dashboard() {
  const { apiFetch } = useApi()
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery<DashboardType>({
    queryKey: ['dashboard'],
    queryFn: () => apiFetch('/api/dashboard'),
  })

  const toggleComplete = useMutation({
    mutationFn: async ({ habitId, completed }: { habitId: string; completed: boolean }) => {
      const today = getTodayISO()
      if (completed) {
        return apiFetch(`/api/habits/${habitId}/complete`, {
          method: 'DELETE',
          body: JSON.stringify({ date: today }),
        })
      } else {
        return apiFetch(`/api/habits/${habitId}/complete`, {
          method: 'POST',
          body: JSON.stringify({ date: today }),
        })
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['habits'] })
    },
  })

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="bg-surface rounded-card border border-border p-5 animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-24 mb-2"></div>
              <div className="h-8 bg-gray-200 rounded w-16"></div>
            </div>
          ))}
        </div>
        <div className="bg-surface rounded-card border border-border p-5 animate-pulse">
          <div className="h-6 bg-gray-200 rounded w-32 mb-4"></div>
          <div className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-12 bg-gray-200 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-card p-6 text-center">
        <p className="text-danger">Failed to load dashboard</p>
        <p className="text-sm text-muted mt-1">{error instanceof Error ? error.message : 'Unknown error'}</p>
      </div>
    )
  }

  if (!data || data.total_habits === 0) {
    return (
      <div className="bg-surface rounded-card border border-border p-12 text-center">
        <h2 className="text-lg font-medium text-gray-900 mb-2">No habits yet</h2>
        <p className="text-muted mb-6">Start tracking your daily habits to build streaks.</p>
        <Link
          to="/habits"
          className="inline-flex items-center px-4 py-2 bg-primary text-white font-medium rounded hover:bg-primary-hover transition-colors"
        >
          Add habit
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-surface rounded-card border border-border p-5">
          <p className="text-sm text-muted mb-1">Total Habits</p>
          <p className="text-3xl font-mono font-medium text-gray-900 font-tabular">
            {data.total_habits}
          </p>
        </div>
        <div className="bg-surface rounded-card border border-border p-5">
          <p className="text-sm text-muted mb-1">Total Completions</p>
          <p className="text-3xl font-mono font-medium text-gray-900 font-tabular">
            {data.total_completions}
          </p>
        </div>
        <div className="bg-surface rounded-card border border-border p-5">
          <p className="text-sm text-muted mb-1">Active Streaks</p>
          <p className="text-3xl font-mono font-medium text-gray-900 font-tabular">
            {data.habits_with_active_streak}
          </p>
        </div>
      </div>

      <div className="bg-surface rounded-card border border-border">
        <div className="px-5 py-4 border-b border-border">
          <h2 className="text-lg font-medium text-gray-900">Today's Habits</h2>
        </div>
        <div className="divide-y divide-border">
          {data.habits.map((habit: Habit) => (
            <div key={habit.id} className="px-5 py-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: getColorHex(habit.color) }}
                />
                <Link
                  to={`/habits/${habit.id}`}
                  className="font-medium text-gray-900 hover:text-primary transition-colors"
                >
                  {habit.name}
                </Link>
              </div>
              <div className="flex items-center gap-6">
                <div className="text-right hidden sm:block">
                  <p className="text-xs text-muted">Current</p>
                  <p className="font-mono text-lg font-medium text-gray-900 font-tabular">
                    {habit.current_streak}
                  </p>
                </div>
                <div className="text-right hidden sm:block">
                  <p className="text-xs text-muted">Longest</p>
                  <p className="font-mono text-lg font-medium text-gray-900 font-tabular">
                    {habit.longest_streak}
                  </p>
                </div>
                <button
                  onClick={() => toggleComplete.mutate({ habitId: habit.id, completed: habit.completed_today })}
                  disabled={toggleComplete.isPending}
                  className={`w-10 h-10 rounded-full border-2 flex items-center justify-center transition-all ${
                    habit.completed_today
                      ? 'bg-success border-success text-white'
                      : 'border-border hover:border-primary'
                  }`}
                  aria-label={habit.completed_today ? 'Mark incomplete' : 'Mark complete'}
                >
                  {habit.completed_today && (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
