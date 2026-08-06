import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';
import { HABIT_COLORS, type Habit } from '../types';
import { Layout } from '../components/Layout';
import { Button } from '../components/Button';
import { useToast } from '../components/Toast';

export function DashboardPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const { data: dashboard, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: api.getDashboard,
  });

  const completeMutation = useMutation({
    mutationFn: ({ id, date }: { id: string; date: string }) => api.completeHabit(id, date),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['habits'] });
    },
    onError: (err: Error) => {
      showToast(err.message, 'error');
    },
  });

  const uncompleteMutation = useMutation({
    mutationFn: ({ id, date }: { id: string; date: string }) => api.uncompleteHabit(id, date),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['habits'] });
    },
    onError: (err: Error) => {
      showToast(err.message, 'error');
    },
  });

  const today = new Date().toISOString().split('T')[0];

  const toggleComplete = (habit: Habit) => {
    if (habit.completed_today) {
      uncompleteMutation.mutate({ id: habit.id, date: today });
    } else {
      completeMutation.mutate({ id: habit.id, date: today });
    }
  };

  if (isLoading) {
    return (
      <Layout>
        <div className="animate-pulse space-y-6">
          <div className="h-8 bg-gray-200 rounded w-48" />
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-24 bg-gray-200 rounded-card" />
            ))}
          </div>
          <div className="h-64 bg-gray-200 rounded-card" />
        </div>
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout>
        <div className="bg-red-50 border border-red-200 rounded-card p-6 text-center">
          <p className="text-danger">Failed to load dashboard</p>
          <p className="text-sm text-muted mt-1">{(error as Error).message}</p>
        </div>
      </Layout>
    );
  }

  if (!dashboard || dashboard.total_habits === 0) {
    return (
      <Layout>
        <div className="text-center py-16">
          <h1 className="text-2xl font-semibold text-gray-900 mb-2">Welcome to Ethara</h1>
          <p className="text-muted mb-6">Start tracking your daily habits</p>
          <Link to="/habits">
            <Button>Add your first habit</Button>
          </Link>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="space-y-8">
        <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <StatCard label="Total Habits" value={dashboard.total_habits} />
          <StatCard label="Total Completions" value={dashboard.total_completions} />
          <StatCard label="Active Streaks" value={dashboard.habits_with_active_streak} />
        </div>

        <div className="bg-surface rounded-card border border-border overflow-hidden">
          <div className="px-4 py-3 border-b border-border">
            <h2 className="text-sm font-medium text-gray-900">Today's Habits</h2>
          </div>
          <div className="divide-y divide-border">
            {dashboard.habits.map((habit) => (
              <HabitRow
                key={habit.id}
                habit={habit}
                onToggle={() => toggleComplete(habit)}
                isToggling={completeMutation.isPending || uncompleteMutation.isPending}
              />
            ))}
          </div>
        </div>
      </div>
    </Layout>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-surface rounded-card border border-border p-4">
      <p className="text-sm text-muted">{label}</p>
      <p className="text-3xl font-semibold font-mono font-tabular text-gray-900 mt-1">{value}</p>
    </div>
  );
}

function HabitRow({
  habit,
  onToggle,
  isToggling,
}: {
  habit: Habit;
  onToggle: () => void;
  isToggling: boolean;
}) {
  return (
    <div className="px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors">
      <div className="flex items-center gap-3">
        <div
          className="w-3 h-3 rounded-full"
          style={{ backgroundColor: HABIT_COLORS[habit.color] }}
        />
        <Link
          to={`/habits/${habit.id}`}
          className="text-sm font-medium text-gray-900 hover:text-primary transition-colors"
        >
          {habit.name}
        </Link>
      </div>

      <div className="flex items-center gap-6">
        <div className="text-right">
          <p className="text-xs text-muted">Current</p>
          <p className="text-lg font-mono font-tabular font-semibold text-gray-900">
            {habit.current_streak}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs text-muted">Longest</p>
          <p className="text-lg font-mono font-tabular font-semibold text-gray-900">
            {habit.longest_streak}
          </p>
        </div>
        <button
          onClick={onToggle}
          disabled={isToggling}
          className={`
            w-11 h-11 rounded-lg flex items-center justify-center transition-all duration-150
            focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary
            ${habit.completed_today
              ? 'bg-success text-white'
              : 'bg-gray-100 text-muted hover:bg-gray-200'
            }
            disabled:opacity-50
          `}
          aria-label={habit.completed_today ? 'Mark incomplete' : 'Mark complete'}
        >
          {habit.completed_today ? (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          ) : (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
            </svg>
          )}
        </button>
      </div>
    </div>
  );
}
