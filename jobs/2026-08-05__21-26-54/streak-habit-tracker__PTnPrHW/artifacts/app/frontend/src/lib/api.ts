import type { Habit, Dashboard, LoginResponse, CreateHabitRequest, UpdateHabitRequest, Completion } from '../types';

const API_BASE = '/api';

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

let authToken: string | null = localStorage.getItem('auth_token');
let onUnauthorized: (() => void) | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
  if (token) {
    localStorage.setItem('auth_token', token);
  } else {
    localStorage.removeItem('auth_token');
  }
}

export function getAuthToken(): string | null {
  return authToken;
}

export function setOnUnauthorized(callback: () => void) {
  onUnauthorized = callback;
}

async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (response.status === 401 || response.status === 403) {
    if (onUnauthorized) {
      onUnauthorized();
    }
    throw new ApiError(response.status, 'Unauthorized');
  }

  if (!response.ok) {
    let message = 'Request failed';
    try {
      const data = await response.json();
      message = data.message || data.error || message;
    } catch {
      // ignore
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

export const api = {
  login: async (email: string, password: string): Promise<LoginResponse> => {
    return fetchApi<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  },

  getDashboard: async (): Promise<Dashboard> => {
    return fetchApi<Dashboard>('/dashboard');
  },

  getHabits: async (): Promise<Habit[]> => {
    return fetchApi<Habit[]>('/habits');
  },

  getHabit: async (id: string): Promise<Habit> => {
    return fetchApi<Habit>(`/habits/${id}`);
  },

  createHabit: async (data: CreateHabitRequest): Promise<Habit> => {
    return fetchApi<Habit>('/habits', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  updateHabit: async (id: string, data: UpdateHabitRequest): Promise<Habit> => {
    return fetchApi<Habit>(`/habits/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  deleteHabit: async (id: string): Promise<void> => {
    return fetchApi<void>(`/habits/${id}`, {
      method: 'DELETE',
    });
  },

  completeHabit: async (id: string, date: string): Promise<void> => {
    return fetchApi<void>(`/habits/${id}/complete`, {
      method: 'POST',
      body: JSON.stringify({ date }),
    });
  },

  uncompleteHabit: async (id: string, date: string): Promise<void> => {
    return fetchApi<void>(`/habits/${id}/complete`, {
      method: 'DELETE',
      body: JSON.stringify({ date }),
    });
  },

  getCompletions: async (habitId: string): Promise<Completion[]> => {
    return fetchApi<Completion[]>(`/habits/${habitId}/completions`);
  },
};

export { ApiError };
