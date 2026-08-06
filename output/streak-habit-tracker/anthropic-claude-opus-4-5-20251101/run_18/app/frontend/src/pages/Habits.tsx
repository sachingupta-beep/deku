import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useApi } from '../hooks/useApi'
import { Habit, CreateHabitInput, CreateHabitSchema, HABIT_COLORS, HabitColor } from '../types'
import { Link } from 'react-router-dom'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'

function getColorHex(color: string): string {
  return HABIT_COLORS.find(c => c.value === color)?.hex || '#4F46E5'
}

export default function Habits() {
  const { apiFetch } = useApi()
  const queryClient = useQueryClient()
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingHabit, setEditingHabit] = useState<Habit | null>(null)
  const [deletingHabit, setDeletingHabit] = useState<Habit | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { data: habits, isLoading, error: fetchError } = useQuery<Habit[]>({
    queryKey: ['habits'],
    queryFn: () => apiFetch('/api/habits'),
  })

  const createHabit = useMutation({
    mutationFn: (data: CreateHabitInput) =>
      apiFetch('/api/habits', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['habits'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      setShowAddModal(false)
      setError(null)
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : 'Failed to create habit')
    },
  })

  const updateHabit = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CreateHabitInput> }) =>
      apiFetch(`/api/habits/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['habits'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      setEditingHabit(null)
      setError(null)
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : 'Failed to update habit')
    },
  })

  const deleteHabit = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/api/habits/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['habits'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      setDeletingHabit(null)
    },
  })

  if (isLoading) {
    return (
      <div className="bg-surface rounded-card border border-border">
        <div className="px-5 py-4 border-b border-border flex justify-between items-center">
          <div className="h-6 bg-gray-200 rounded w-24 animate-pulse"></div>
          <div className="h-9 bg-gray-200 rounded w-24 animate-pulse"></div>
        </div>
        <div className="divide-y divide-border">
          {[1, 2, 3].map(i => (
            <div key={i} className="px-5 py-4 animate-pulse">
              <div className="h-5 bg-gray-200 rounded w-32"></div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (fetchError) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-card p-6 text-center">
        <p className="text-danger">Failed to load habits</p>
        <p className="text-sm text-muted mt-1">{fetchError instanceof Error ? fetchError.message : 'Unknown error'}</p>
      </div>
    )
  }

  return (
    <>
      <div className="bg-surface rounded-card border border-border">
        <div className="px-5 py-4 border-b border-border flex justify-between items-center">
          <h2 className="text-lg font-medium text-gray-900">Habits</h2>
          <button
            onClick={() => {
              setError(null)
              setShowAddModal(true)
            }}
            className="px-4 py-2 bg-primary text-white text-sm font-medium rounded hover:bg-primary-hover transition-colors"
          >
            Add habit
          </button>
        </div>

        {!habits || habits.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <p className="text-muted mb-4">No habits yet. Add your first habit to start tracking.</p>
            <button
              onClick={() => {
                setError(null)
                setShowAddModal(true)
              }}
              className="px-4 py-2 bg-primary text-white text-sm font-medium rounded hover:bg-primary-hover transition-colors"
            >
              Add habit
            </button>
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-gray-50/50">
                <th className="px-5 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">Name</th>
                <th className="px-5 py-3 text-right text-xs font-medium text-muted uppercase tracking-wider hidden sm:table-cell">Current</th>
                <th className="px-5 py-3 text-right text-xs font-medium text-muted uppercase tracking-wider hidden sm:table-cell">Longest</th>
                <th className="px-5 py-3 text-right text-xs font-medium text-muted uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {habits.map((habit) => (
                <tr key={habit.id} className="h-[36px]">
                  <td className="px-5 py-2">
                    <div className="flex items-center gap-3">
                      <div
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{ backgroundColor: getColorHex(habit.color) }}
                      />
                      <Link
                        to={`/habits/${habit.id}`}
                        className="font-medium text-gray-900 hover:text-primary transition-colors truncate"
                      >
                        {habit.name}
                      </Link>
                    </div>
                  </td>
                  <td className="px-5 py-2 text-right font-mono text-sm font-tabular hidden sm:table-cell">
                    {habit.current_streak}
                  </td>
                  <td className="px-5 py-2 text-right font-mono text-sm font-tabular hidden sm:table-cell">
                    {habit.longest_streak}
                  </td>
                  <td className="px-5 py-2 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => {
                          setError(null)
                          setEditingHabit(habit)
                        }}
                        className="p-1.5 text-muted hover:text-gray-900 transition-colors"
                        aria-label="Edit habit"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                        </svg>
                      </button>
                      <button
                        onClick={() => setDeletingHabit(habit)}
                        className="p-1.5 text-muted hover:text-danger transition-colors"
                        aria-label="Delete habit"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showAddModal && (
        <HabitModal
          onClose={() => {
            setShowAddModal(false)
            setError(null)
          }}
          onSubmit={(data) => createHabit.mutate(data)}
          isLoading={createHabit.isPending}
          error={error}
        />
      )}

      {editingHabit && (
        <HabitModal
          habit={editingHabit}
          onClose={() => {
            setEditingHabit(null)
            setError(null)
          }}
          onSubmit={(data) => updateHabit.mutate({ id: editingHabit.id, data })}
          isLoading={updateHabit.isPending}
          error={error}
        />
      )}

      {deletingHabit && (
        <DeleteModal
          habit={deletingHabit}
          onClose={() => setDeletingHabit(null)}
          onConfirm={() => deleteHabit.mutate(deletingHabit.id)}
          isLoading={deleteHabit.isPending}
        />
      )}
    </>
  )
}

function HabitModal({
  habit,
  onClose,
  onSubmit,
  isLoading,
  error,
}: {
  habit?: Habit
  onClose: () => void
  onSubmit: (data: CreateHabitInput) => void
  isLoading: boolean
  error: string | null
}) {
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<CreateHabitInput>({
    resolver: zodResolver(CreateHabitSchema),
    defaultValues: {
      name: habit?.name || '',
      description: habit?.description || '',
      color: habit?.color || 'indigo',
    },
  })

  const selectedColor = watch('color')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/30 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative bg-surface rounded-card border border-border shadow-lg w-full max-w-md p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">
          {habit ? 'Edit habit' : 'Add habit'}
        </h3>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-danger">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
              Name
            </label>
            <input
              id="name"
              type="text"
              {...register('name')}
              className="w-full px-3 py-2 border border-border rounded focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              placeholder="e.g., Meditate"
              maxLength={80}
            />
            {errors.name && (
              <p className="mt-1 text-sm text-danger">{errors.name.message}</p>
            )}
          </div>

          <div>
            <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-1">
              Description (optional)
            </label>
            <input
              id="description"
              type="text"
              {...register('description')}
              className="w-full px-3 py-2 border border-border rounded focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              placeholder="e.g., 10 minutes of mindfulness"
              maxLength={200}
            />
            {errors.description && (
              <p className="mt-1 text-sm text-danger">{errors.description.message}</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Color
            </label>
            <div className="flex gap-2">
              {HABIT_COLORS.map((color) => (
                <button
                  key={color.value}
                  type="button"
                  onClick={() => setValue('color', color.value as HabitColor)}
                  className={`w-8 h-8 rounded-full transition-all ${
                    selectedColor === color.value
                      ? 'ring-2 ring-offset-2 ring-gray-400'
                      : ''
                  }`}
                  style={{ backgroundColor: color.hex }}
                  aria-label={color.label}
                />
              ))}
            </div>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 border border-border text-gray-700 font-medium rounded hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="flex-1 px-4 py-2 bg-primary text-white font-medium rounded hover:bg-primary-hover transition-colors disabled:opacity-50"
            >
              {isLoading ? 'Saving...' : habit ? 'Save' : 'Add'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function DeleteModal({
  habit,
  onClose,
  onConfirm,
  isLoading,
}: {
  habit: Habit
  onClose: () => void
  onConfirm: () => void
  isLoading: boolean
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/30 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative bg-surface rounded-card border border-border shadow-lg w-full max-w-sm p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-2">Delete habit</h3>
        <p className="text-muted mb-6">
          Are you sure you want to delete "{habit.name}"? This action cannot be undone.
        </p>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 px-4 py-2 border border-border text-gray-700 font-medium rounded hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
            className="flex-1 px-4 py-2 bg-danger text-white font-medium rounded hover:bg-red-700 transition-colors disabled:opacity-50"
          >
            {isLoading ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  )
}
