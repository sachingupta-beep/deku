import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { api, ApiError } from '../lib/api';
import { HABIT_COLORS, CreateHabitRequestSchema, type CreateHabitRequest, type Habit, type HabitColor } from '../types';
import { Layout } from '../components/Layout';
import { Button } from '../components/Button';
import { Input } from '../components/Input';
import { Modal } from '../components/Modal';
import { ColorPicker } from '../components/ColorPicker';
import { useToast } from '../components/Toast';

export function HabitsPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingHabit, setEditingHabit] = useState<Habit | null>(null);
  const [deletingHabit, setDeletingHabit] = useState<Habit | null>(null);

  const { data: habits, isLoading, error } = useQuery({
    queryKey: ['habits'],
    queryFn: api.getHabits,
  });

  const createMutation = useMutation({
    mutationFn: api.createHabit,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['habits'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      setIsAddModalOpen(false);
      showToast('Habit created', 'success');
    },
    onError: (err: Error) => {
      showToast(err.message, 'error');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CreateHabitRequest> }) =>
      api.updateHabit(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['habits'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      setEditingHabit(null);
      showToast('Habit updated', 'success');
    },
    onError: (err: Error) => {
      showToast(err.message, 'error');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: api.deleteHabit,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['habits'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      setDeletingHabit(null);
      showToast('Habit deleted', 'success');
    },
    onError: (err: Error) => {
      showToast(err.message, 'error');
    },
  });

  if (isLoading) {
    return (
      <Layout>
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-gray-200 rounded w-32" />
          <div className="h-64 bg-gray-200 rounded-card" />
        </div>
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout>
        <div className="bg-red-50 border border-red-200 rounded-card p-6 text-center">
          <p className="text-danger">Failed to load habits</p>
          <p className="text-sm text-muted mt-1">{(error as Error).message}</p>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold text-gray-900">Habits</h1>
          <Button onClick={() => setIsAddModalOpen(true)}>Add habit</Button>
        </div>

        {!habits || habits.length === 0 ? (
          <div className="bg-surface rounded-card border border-border p-12 text-center">
            <p className="text-muted mb-4">No habits yet</p>
            <Button onClick={() => setIsAddModalOpen(true)}>Add your first habit</Button>
          </div>
        ) : (
          <div className="bg-surface rounded-card border border-border overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-border sticky top-0">
                <tr>
                  <th className="text-left text-xs font-medium text-muted uppercase tracking-wider px-4 py-3">
                    Name
                  </th>
                  <th className="text-right text-xs font-medium text-muted uppercase tracking-wider px-4 py-3">
                    Current
                  </th>
                  <th className="text-right text-xs font-medium text-muted uppercase tracking-wider px-4 py-3">
                    Longest
                  </th>
                  <th className="text-right text-xs font-medium text-muted uppercase tracking-wider px-4 py-3">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {habits.map((habit) => (
                  <tr key={habit.id} className="h-9 hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-3">
                        <div
                          className="w-3 h-3 rounded-full flex-shrink-0"
                          style={{ backgroundColor: HABIT_COLORS[habit.color] }}
                        />
                        <Link
                          to={`/habits/${habit.id}`}
                          className="text-sm font-medium text-gray-900 hover:text-primary transition-colors"
                        >
                          {habit.name}
                        </Link>
                      </div>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <span className="text-sm font-mono font-tabular text-gray-900">
                        {habit.current_streak}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <span className="text-sm font-mono font-tabular text-gray-900">
                        {habit.longest_streak}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditingHabit(habit)}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeletingHabit(habit)}
                          className="text-danger hover:text-danger"
                        >
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <AddHabitModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onSubmit={(data) => createMutation.mutate(data)}
        isLoading={createMutation.isPending}
        error={createMutation.error instanceof ApiError ? createMutation.error.message : null}
      />

      {editingHabit && (
        <EditHabitModal
          habit={editingHabit}
          isOpen={true}
          onClose={() => setEditingHabit(null)}
          onSubmit={(data) => updateMutation.mutate({ id: editingHabit.id, data })}
          isLoading={updateMutation.isPending}
          error={updateMutation.error instanceof ApiError ? updateMutation.error.message : null}
        />
      )}

      {deletingHabit && (
        <DeleteHabitModal
          habit={deletingHabit}
          isOpen={true}
          onClose={() => setDeletingHabit(null)}
          onConfirm={() => deleteMutation.mutate(deletingHabit.id)}
          isLoading={deleteMutation.isPending}
        />
      )}
    </Layout>
  );
}

function AddHabitModal({
  isOpen,
  onClose,
  onSubmit,
  isLoading,
  error,
}: {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: CreateHabitRequest) => void;
  isLoading: boolean;
  error: string | null;
}) {
  const [color, setColor] = useState<HabitColor>('indigo');
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CreateHabitRequest>({
    resolver: zodResolver(CreateHabitRequestSchema),
    defaultValues: { color: 'indigo' },
  });

  const handleClose = () => {
    reset();
    setColor('indigo');
    onClose();
  };

  const handleFormSubmit = (data: CreateHabitRequest) => {
    onSubmit({ ...data, color });
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Add habit">
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-danger">
          {error}
        </div>
      )}
      <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-4">
        <Input
          label="Name"
          {...register('name')}
          error={errors.name?.message}
          maxLength={80}
        />
        <Input
          label="Description (optional)"
          {...register('description')}
          error={errors.description?.message}
          maxLength={200}
        />
        <ColorPicker value={color} onChange={setColor} />
        <div className="flex justify-end gap-3 pt-4">
          <Button type="button" variant="secondary" onClick={handleClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={isLoading}>
            {isLoading ? 'Creating...' : 'Create'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function EditHabitModal({
  habit,
  isOpen,
  onClose,
  onSubmit,
  isLoading,
  error,
}: {
  habit: Habit;
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: Partial<CreateHabitRequest>) => void;
  isLoading: boolean;
  error: string | null;
}) {
  const [color, setColor] = useState<HabitColor>(habit.color);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CreateHabitRequest>({
    resolver: zodResolver(CreateHabitRequestSchema),
    defaultValues: {
      name: habit.name,
      description: habit.description || '',
      color: habit.color,
    },
  });

  const handleFormSubmit = (data: CreateHabitRequest) => {
    onSubmit({ ...data, color });
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Edit habit">
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-danger">
          {error}
        </div>
      )}
      <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-4">
        <Input
          label="Name"
          {...register('name')}
          error={errors.name?.message}
          maxLength={80}
        />
        <Input
          label="Description (optional)"
          {...register('description')}
          error={errors.description?.message}
          maxLength={200}
        />
        <ColorPicker value={color} onChange={setColor} />
        <div className="flex justify-end gap-3 pt-4">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={isLoading}>
            {isLoading ? 'Saving...' : 'Save'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function DeleteHabitModal({
  habit,
  isOpen,
  onClose,
  onConfirm,
  isLoading,
}: {
  habit: Habit;
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  isLoading: boolean;
}) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Delete habit">
      <p className="text-sm text-muted mb-6">
        Are you sure you want to delete <strong className="text-gray-900">{habit.name}</strong>?
        This action cannot be undone.
      </p>
      <div className="flex justify-end gap-3">
        <Button type="button" variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button type="button" variant="destructive" onClick={onConfirm} disabled={isLoading}>
          {isLoading ? 'Deleting...' : 'Delete'}
        </Button>
      </div>
    </Modal>
  );
}
