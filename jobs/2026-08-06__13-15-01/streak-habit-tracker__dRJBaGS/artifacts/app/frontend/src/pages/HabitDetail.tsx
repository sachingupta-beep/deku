import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useApi } from '../hooks/useApi'
import { Habit, HABIT_COLORS } from '../types'
import { useParams, Link } from 'react-router-dom'
import { useMemo, useState } from 'react'

function getColorHex(color: string): string {
  return HABIT_COLORS.find(c => c.value === color)?.hex || '#4F46E5'
}

function getTodayISO(): string {
  return new Date().toISOString().split('T')[0]
}

function getDateRange(months: number): string[] {
  const dates: string[] = []
  const today = new Date()
  const start = new Date(today)
  start.setMonth(start.getMonth() - months + 1)
  start.setDate(1)

  const current = new Date(start)
  while (current <= today) {
    dates.push(current.toISOString().split('T')[0])
    current.setDate(current.getDate() + 1)
  }
  return dates
}

interface CompletionData {
  completions: string[]
}

export default function HabitDetail() {
  const { id } = useParams<{ id: string }>()
  const { apiFetch } = useApi()
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const { data: habit, isLoading: habitLoading, error: habitError } = useQuery<Habit>({
    queryKey: ['habit', id],
    queryFn: () => apiFetch(`/api/habits/${id}`),
    enabled: !!id,
  })

  const { data: completionData } = useQuery<CompletionData>({
    queryKey: ['completions', id],
    queryFn: () => apiFetch(`/api/habits/${id}/completions`),
    enabled: !!id,
  })

  const completions = useMemo(() => {
    return new Set(completionData?.completions || [])
  }, [completionData])

  const toggleComplete = useMutation({
    mutationFn: async ({ date, completed }: { date: string; completed: boolean }) => {
      if (completed) {
        return apiFetch(`/api/habits/${id}/complete`, {
          method: 'DELETE',
          body: JSON.stringify({ date }),
        })
      } else {
        return apiFetch(`/api/habits/${id}/complete`, {
          method: 'POST',
          body: JSON.stringify({ date }),
        })
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['habit', id] })
      queryClient.invalidateQueries({ queryKey: ['completions', id] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['habits'] })
      setError(null)
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : 'Failed to update completion')
    },
  })

  const dates = useMemo(() => getDateRange(3), [])
  const today = getTodayISO()

  const weeks = useMemo(() => {
    const result: string[][] = []
    let currentWeek: string[] = []

    const firstDate = new Date(dates[0])
    const startPadding = firstDate.getDay()
    for (let i = 0; i < startPadding; i++) {
      currentWeek.push('')
    }

    for (const date of dates) {
      currentWeek.push(date)
      if (currentWeek.length === 7) {
        result.push(currentWeek)
        currentWeek = []
      }
    }

    if (currentWeek.length > 0) {
      while (currentWeek.length < 7) {
        currentWeek.push('')
      }
      result.push(currentWeek)
    }

    return result
  }, [dates])

  if (habitLoading) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 rounded w-48 mb-4"></div>
          <div className="h-4 bg-gray-200 rounded w-32"></div>
        </div>
      </div>
    )
  }

  if (habitError || !habit) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-card p-6 text-center">
        <p className="text-danger">Failed to load habit</p>
        <Link to="/habits" className="text-primary hover:underline mt-2 inline-block">
          Back to habits
        </Link>
      </div>
    )
  }

  const colorHex = getColorHex(habit.color)

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-muted">
        <Link to="/habits" className="hover:text-gray-900 transition-colors">
          Habits
        </Link>
        <span>/</span>
        <span className="text-gray-900">{habit.name}</span>
      </div>

      <div className="bg-surface rounded-card border border-border p-6">
        <div className="flex items-start justify-between mb-6">
          <div className="flex items-center gap-3">
            <div
              className="w-4 h-4 rounded-full"
              style={{ backgroundColor: colorHex }}
            />
            <h1 className="text-2xl font-semibold text-gray-900">{habit.name}</h1>
          </div>
        </div>

        {habit.description && (
          <p className="text-muted mb-6">{habit.description}</p>
        )}

        <div className="grid grid-cols-2 gap-4 mb-8">
          <div className="bg-background rounded-lg p-4">
            <p className="text-sm text-muted mb-1">Current Streak</p>
            <p className="text-3xl font-mono font-medium text-gray-900 font-tabular">
              {habit.current_streak}
            </p>
          </div>
          <div className="bg-background rounded-lg p-4">
            <p className="text-sm text-muted mb-1">Longest Streak</p>
            <p className="text-3xl font-mono font-medium text-gray-900 font-tabular">
              {habit.longest_streak}
            </p>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-danger">
            {error}
          </div>
        )}

        <div>
          <h2 className="text-lg font-medium text-gray-900 mb-4">Completion History</h2>
          <div className="overflow-x-auto">
            <div className="inline-block">
              <div className="flex gap-0.5 text-xs text-muted mb-1">
                <div className="w-4"></div>
                {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((day, i) => (
                  <div key={i} className="w-4 text-center">{day}</div>
                ))}
              </div>
              <div className="flex flex-col gap-0.5">
                {weeks.map((week, weekIndex) => (
                  <div key={weekIndex} className="flex gap-0.5">
                    <div className="w-4 text-xs text-muted flex items-center">
                      {week[0] && new Date(week[0]).getDate() <= 7 && (
                        <span>{new Date(week[0]).toLocaleDateString('en-US', { month: 'short' }).slice(0, 3)}</span>
                      )}
                    </div>
                    {week.map((date, dayIndex) => {
                      if (!date) {
                        return <div key={dayIndex} className="w-4 h-4" />
                      }

                      const isCompleted = completions.has(date)
                      const isFuture = date > today
                      const isToday = date === today

                      return (
                        <button
                          key={dayIndex}
                          onClick={() => {
                            if (!isFuture) {
                              toggleComplete.mutate({ date, completed: isCompleted })
                            }
                          }}
                          disabled={isFuture || toggleComplete.isPending}
                          className={`w-4 h-4 rounded-sm transition-all ${
                            isFuture
                              ? 'bg-gray-100 cursor-not-allowed'
                              : isCompleted
                              ? 'hover:opacity-80'
                              : 'bg-gray-200 hover:bg-gray-300'
                          } ${isToday ? 'ring-1 ring-gray-400' : ''}`}
                          style={isCompleted ? { backgroundColor: colorHex } : undefined}
                          title={date}
                          aria-label={`${date}${isCompleted ? ' (completed)' : ''}`}
                        />
                      )
                    })}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
