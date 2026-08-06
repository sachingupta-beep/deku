import { z } from 'zod'

export const HabitColorSchema = z.enum(['indigo', 'teal', 'amber', 'rose', 'slate', 'forest'])
export type HabitColor = z.infer<typeof HabitColorSchema>

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
})
export type Habit = z.infer<typeof HabitSchema>

export const CreateHabitSchema = z.object({
  name: z.string().min(1, 'Name is required').max(80, 'Name must be 80 characters or less'),
  description: z.string().max(200, 'Description must be 200 characters or less').optional(),
  color: HabitColorSchema,
})
export type CreateHabitInput = z.infer<typeof CreateHabitSchema>

export const UpdateHabitSchema = z.object({
  name: z.string().min(1).max(80).optional(),
  description: z.string().max(200).optional(),
  color: HabitColorSchema.optional(),
})
export type UpdateHabitInput = z.infer<typeof UpdateHabitSchema>

export const CompletionSchema = z.object({
  id: z.string(),
  habit_id: z.string(),
  user_id: z.string(),
  date: z.string(),
})
export type Completion = z.infer<typeof CompletionSchema>

export const DashboardSchema = z.object({
  total_habits: z.number(),
  total_completions: z.number(),
  habits_with_active_streak: z.number(),
  habits: z.array(HabitSchema),
})
export type Dashboard = z.infer<typeof DashboardSchema>

export const LoginSchema = z.object({
  email: z.string().email('Invalid email'),
  password: z.string().min(1, 'Password is required'),
})
export type LoginInput = z.infer<typeof LoginSchema>

export const AuthResponseSchema = z.object({
  access_token: z.string(),
  user: z.object({
    id: z.string(),
    email: z.string(),
  }).optional(),
})
export type AuthResponse = z.infer<typeof AuthResponseSchema>

export const HABIT_COLORS: { value: HabitColor; label: string; hex: string }[] = [
  { value: 'indigo', label: 'Indigo', hex: '#4F46E5' },
  { value: 'teal', label: 'Teal', hex: '#0D9488' },
  { value: 'amber', label: 'Amber', hex: '#D97706' },
  { value: 'rose', label: 'Rose', hex: '#E11D48' },
  { value: 'slate', label: 'Slate', hex: '#475569' },
  { value: 'forest', label: 'Forest', hex: '#166534' },
]
