import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import { HABIT_COLORS } from '../types';
import { Layout } from '../components/Layout';
import { Button } from '../components/Button';
import { useToast } from '../components/Toast';

export function HabitDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const { data: habit, isLoading: habitLoading, error: habitError } = useQuery({
    queryKey: ['habit', id],
    queryFn: () => api.getHabit(id!),
    enabled: !!id,
  });

  const { data: completions, isLoading: completionsLoading } = useQuery({
    queryKey: ['completions', id],
    queryFn: () => api.getCompletions(id!),
    enabled: !!id,
  });

  const completeMutation = useMutation({
    mutationFn: ({ date }: { date: string }) => api.completeHabit(id!, date),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['habit', id] });
      queryClient.invalidateQueries({ queryKey: ['completions', id] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['habits'] });
    },
    onError: (err: Error) => {
      showToast(err.message, 'error');
    },
  });

  const uncompleteMutation = useMutation({
    mutationFn: ({ date }: { date: string }) => api.uncompleteHabit(id!, date),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['habit', id] });
      queryClient.invalidateQueries({ queryKey: ['completions', id] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['habits'] });
    },
    onError: (err: Error) => {
      showToast(err.message, 'error');
    },
  });

  const isLoading = habitLoading || completionsLoading;

  if (isLoading) {
    return (
      <Layout>
        <div className="animate-pulse space-y-6">
          <div className="h-8 bg-gray-200 rounded w-48" />
          <div className="h-32 bg-gray-200 rounded-card" />
          <div className="h-64 bg-gray-200 rounded-card" />
        </div>
      </Layout>
    );
  }

  if (habitError || !habit) {
    return (
      <Layout>
        <div className="bg-red-50 border border-red-200 rounded-card p-6 text-center">
          <p className="text-danger">Failed to load habit</p>
          <p className="text-sm text-muted mt-1">{(habitError as Error)?.message || 'Not found'}</p>
          <Link to="/habits" className="mt-4 inline-block">
            <Button variant="secondary">Back to habits</Button>
          </Link>
        </div>
      </Layout>
    );
  }

  const completionDates = new Set(completions?.map((c) => c.date) || []);
  const today = new Date().toISOString().split('T')[0];

  const toggleDate = (date: string) => {
    if (date > today) {
      showToast('Cannot mark future dates', 'error');
      return;
    }
    if (completionDates.has(date)) {
      uncompleteMutation.mutate({ date });
    } else {
      completeMutation.mutate({ date });
    }
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Link to="/habits" className="text-muted hover:text-gray-900 transition-colors">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </Link>
          <div className="flex items-center gap-3">
            <div
              className="w-4 h-4 rounded-full"
              style={{ backgroundColor: HABIT_COLORS[habit.color] }}
            />
            <h1 className="text-2xl font-semibold text-gray-900">{habit.name}</h1>
          </div>
        </div>

        {habit.description && (
          <p className="text-muted">{habit.description}</p>
        )}

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <StatCard label="Current Streak" value={habit.current_streak} />
          <StatCard label="Longest Streak" value={habit.longest_streak} />
          <StatCard label="Completed Today" value={habit.completed_today ? 'Yes' : 'No'} />
          <StatCard label="Total Completions" value={completions?.length || 0} />
        </div>

        <div className="bg-surface rounded-card border border-border p-6">
          <h2 className="text-sm font-medium text-gray-900 mb-4">Completion Calendar</h2>
          <CompletionCalendar
            completionDates={completionDates}
            habitColor={HABIT_COLORS[habit.color]}
            onToggle={toggleDate}
            today={today}
            isToggling={completeMutation.isPending || uncompleteMutation.isPending}
          />
        </div>
      </div>
    </Layout>
  );
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="bg-surface rounded-card border border-border p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className="text-2xl font-semibold font-mono font-tabular text-gray-900 mt-1">{value}</p>
    </div>
  );
}

function CompletionCalendar({
  completionDates,
  habitColor,
  onToggle,
  today,
  isToggling,
}: {
  completionDates: Set<string>;
  habitColor: string;
  onToggle: (date: string) => void;
  today: string;
  isToggling: boolean;
}) {
  // Generate last 12 weeks of dates
  const weeks: string[][] = [];
  const todayDate = new Date(today);
  
  for (let w = 11; w >= 0; w--) {
    const week: string[] = [];
    for (let d = 0; d < 7; d++) {
      const date = new Date(todayDate);
      date.setDate(date.getDate() - (w * 7 + (6 - d)));
      week.push(date.toISOString().split('T')[0]);
    }
    weeks.push(week);
  }

  const dayLabels = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

  return (
    <div className="overflow-x-auto">
      <div className="inline-block">
        <div className="flex gap-1 mb-1">
          <div className="w-4" />
          {weeks.map((week, i) => (
            <div key={i} className="w-6 h-4 text-[10px] text-muted text-center">
              {i === 0 || new Date(week[0]).getDate() <= 7 ? (
                new Date(week[0]).toLocaleDateString('en-US', { month: 'short' })
              ) : ''}
            </div>
          ))}
        </div>
        {dayLabels.map((label, dayIndex) => (
          <div key={dayIndex} className="flex gap-1 items-center">
            <div className="w-4 text-[10px] text-muted">{label}</div>
            {weeks.map((week, weekIndex) => {
              const date = week[dayIndex];
              const isCompleted = completionDates.has(date);
              const isFuture = date > today;
              const isToday = date === today;

              return (
                <button
                  key={`${weekIndex}-${dayIndex}`}
                  onClick={() => !isFuture && onToggle(date)}
                  disabled={isFuture || isToggling}
                  className={`
                    w-6 h-6 rounded-sm transition-all duration-150
                    focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1
                    ${isFuture ? 'bg-gray-50 cursor-not-allowed' : 'hover:scale-110 cursor-pointer'}
                    ${isToday ? 'ring-1 ring-gray-400' : ''}
                  `}
                  style={{
                    backgroundColor: isCompleted ? habitColor : isFuture ? undefined : '#E5E7EB',
                  }}
                  title={date}
                  aria-label={`${date}${isCompleted ? ' (completed)' : ''}`}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
