import { z } from 'zod';

export const HabitColorSchema = z.enum(['indigo', 'teal', 'amber', 'rose', 'slate', 'forest']);
export type HabitColor = z.infer<typeof HabitColorSchema>;

export const HabitSchema = z.object({
  id: z.string(),
  name: z.string().min(1).max(80),
  description: z.string().max(200).optional(),
  color: HabitColorSchema,
  current_streak: z.number(),
  longest_streak: z.number(),
  completed_today: z.boolean(),
  created: z.string().optional(),
  updated: z.string().optional(),
});
export type Habit = z.infer<typeof HabitSchema>;

export const CompletionSchema = z.object({
  id: z.string(),
  habit_id: z.string(),
  user_id: z.string(),
  date: z.string(),
  created: z.string().optional(),
});
export type Completion = z.infer<typeof CompletionSchema>;

export const DashboardSchema = z.object({
  total_habits: z.number(),
  total_completions: z.number(),
  habits_with_active_streak: z.number(),
  habits: z.array(HabitSchema),
});
export type Dashboard = z.infer<typeof DashboardSchema>;

export const LoginRequestSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});
export type LoginRequest = z.infer<typeof LoginRequestSchema>;

export const LoginResponseSchema = z.object({
  access_token: z.string(),
});
export type LoginResponse = z.infer<typeof LoginResponseSchema>;

export const CreateHabitRequestSchema = z.object({
  name: z.string().min(1).max(80),
  color: HabitColorSchema,
  description: z.string().max(200).optional(),
});
export type CreateHabitRequest = z.infer<typeof CreateHabitRequestSchema>;

export const UpdateHabitRequestSchema = z.object({
  name: z.string().min(1).max(80).optional(),
  color: HabitColorSchema.optional(),
  description: z.string().max(200).optional(),
});
export type UpdateHabitRequest = z.infer<typeof UpdateHabitRequestSchema>;

export const CompleteHabitRequestSchema = z.object({
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
});
export type CompleteHabitRequest = z.infer<typeof CompleteHabitRequestSchema>;

export const HABIT_COLORS: Record<HabitColor, string> = {
  indigo: '#4F46E5',
  teal: '#0D9488',
  amber: '#D97706',
  rose: '#E11D48',
  slate: '#475569',
  forest: '#166534',
};
