import express from 'express';
import PocketBase from 'pocketbase';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { existsSync } from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const app = express();
app.use(express.json());

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8090';
const PORT = parseInt(process.env.APP_PUBLIC_PORT || '4173', 10);

const pb = new PocketBase(BACKEND_URL);
pb.autoCancellation(false);

function log(level, message, data = {}) {
  console.log(JSON.stringify({
    timestamp: new Date().toISOString(),
    level,
    message,
    ...data
  }));
}

function getTodayUTC() {
  return new Date().toISOString().split('T')[0];
}

function calculateStreaks(completionDates) {
  if (!completionDates || completionDates.length === 0) {
    return { current_streak: 0, longest_streak: 0 };
  }

  const sortedDates = [...completionDates].sort();
  const today = getTodayUTC();
  
  let currentStreak = 0;
  let longestStreak = 0;
  let streak = 0;
  let prevDate = null;

  for (const dateStr of sortedDates) {
    if (prevDate === null) {
      streak = 1;
    } else {
      const prev = new Date(prevDate);
      const curr = new Date(dateStr);
      const diffDays = Math.round((curr - prev) / (1000 * 60 * 60 * 24));
      
      if (diffDays === 1) {
        streak++;
      } else if (diffDays > 1) {
        streak = 1;
      }
    }
    
    longestStreak = Math.max(longestStreak, streak);
    prevDate = dateStr;
  }

  const lastDate = sortedDates[sortedDates.length - 1];
  if (lastDate === today) {
    currentStreak = streak;
  } else {
    const last = new Date(lastDate);
    const todayDate = new Date(today);
    const diffDays = Math.round((todayDate - last) / (1000 * 60 * 60 * 24));
    if (diffDays > 1) {
      currentStreak = 0;
    } else {
      currentStreak = 0;
    }
  }

  return { current_streak: currentStreak, longest_streak: longestStreak };
}

async function authenticateRequest(req) {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return null;
  }

  const token = authHeader.substring(7);
  
  try {
    const authPb = new PocketBase(BACKEND_URL);
    authPb.autoCancellation(false);
    authPb.authStore.save(token, null);
    
    const user = await authPb.collection('users').authRefresh();
    return { pb: authPb, user: user.record };
  } catch (err) {
    log('debug', 'Auth failed', { error: err.message });
    return null;
  }
}

async function getHabitWithStreaks(authPb, habit, userId) {
  const today = getTodayUTC();
  
  try {
    const completions = await authPb.collection('completions').getFullList({
      filter: `habit_id = "${habit.id}" && user_id = "${userId}"`,
      sort: 'date',
    });
    
    const dates = completions.map(c => c.date);
    const { current_streak, longest_streak } = calculateStreaks(dates);
    const completed_today = dates.includes(today);
    
    return {
      id: habit.id,
      name: habit.name,
      description: habit.description || '',
      color: habit.color,
      current_streak,
      longest_streak,
      completed_today,
      created: habit.created,
      updated: habit.updated,
    };
  } catch (err) {
    log('error', 'Failed to get habit streaks', { error: err.message });
    return {
      id: habit.id,
      name: habit.name,
      description: habit.description || '',
      color: habit.color,
      current_streak: 0,
      longest_streak: 0,
      completed_today: false,
      created: habit.created,
      updated: habit.updated,
    };
  }
}

// Health check
app.get('/api/health', (req, res) => {
  res.status(200).json({ status: 'ok' });
});

// Login
app.post('/api/auth/login', async (req, res) => {
  const { email, password } = req.body;
  
  if (!email || !password) {
    return res.status(400).json({ message: 'Email and password are required' });
  }

  try {
    const authPb = new PocketBase(BACKEND_URL);
    authPb.autoCancellation(false);
    const authData = await authPb.collection('users').authWithPassword(email, password);
    
    log('info', 'User logged in', { email });
    
    res.json({
      access_token: authData.token,
      user: {
        id: authData.record.id,
        email: authData.record.email,
      }
    });
  } catch (err) {
    log('warn', 'Login failed', { email, error: err.message });
    res.status(401).json({ message: 'Invalid email or password' });
  }
});

// Get dashboard
app.get('/api/dashboard', async (req, res) => {
  const auth = await authenticateRequest(req);
  if (!auth) {
    return res.status(401).json({ message: 'Unauthorized' });
  }

  try {
    const habits = await auth.pb.collection('habits').getFullList({
      filter: `user_id = "${auth.user.id}" && deleted = false`,
      sort: 'created',
    });

    const habitsWithStreaks = await Promise.all(
      habits.map(h => getHabitWithStreaks(auth.pb, h, auth.user.id))
    );

    const completions = await auth.pb.collection('completions').getFullList({
      filter: `user_id = "${auth.user.id}"`,
    });

    const total_habits = habitsWithStreaks.length;
    const total_completions = completions.length;
    const habits_with_active_streak = habitsWithStreaks.filter(h => h.current_streak >= 1).length;

    res.json({
      total_habits,
      total_completions,
      habits_with_active_streak,
      habits: habitsWithStreaks,
    });
  } catch (err) {
    log('error', 'Dashboard error', { error: err.message });
    res.status(500).json({ message: 'Failed to load dashboard' });
  }
});

// List habits
app.get('/api/habits', async (req, res) => {
  const auth = await authenticateRequest(req);
  if (!auth) {
    return res.status(401).json({ message: 'Unauthorized' });
  }

  try {
    const habits = await auth.pb.collection('habits').getFullList({
      filter: `user_id = "${auth.user.id}" && deleted = false`,
      sort: 'created',
    });

    const habitsWithStreaks = await Promise.all(
      habits.map(h => getHabitWithStreaks(auth.pb, h, auth.user.id))
    );

    res.json(habitsWithStreaks);
  } catch (err) {
    log('error', 'List habits error', { error: err.message });
    res.status(500).json({ message: 'Failed to load habits' });
  }
});

// Create habit
app.post('/api/habits', async (req, res) => {
  const auth = await authenticateRequest(req);
  if (!auth) {
    return res.status(401).json({ message: 'Unauthorized' });
  }

  const { name, description, color } = req.body;

  if (!name || name.length < 1 || name.length > 80) {
    return res.status(400).json({ message: 'Name must be 1-80 characters' });
  }

  const validColors = ['indigo', 'teal', 'amber', 'rose', 'slate', 'forest'];
  if (!color || !validColors.includes(color)) {
    return res.status(400).json({ message: 'Invalid color' });
  }

  if (description && description.length > 200) {
    return res.status(400).json({ message: 'Description must be 200 characters or less' });
  }

  try {
    const existing = await auth.pb.collection('habits').getFullList({
      filter: `user_id = "${auth.user.id}" && deleted = false`,
    });

    const nameLower = name.toLowerCase();
    const duplicate = existing.find(h => h.name.toLowerCase() === nameLower);
    if (duplicate) {
      return res.status(409).json({ message: 'A habit with this name already exists' });
    }

    const habit = await auth.pb.collection('habits').create({
      user_id: auth.user.id,
      name,
      description: description || '',
      color,
      deleted: false,
    });

    log('info', 'Habit created', { habitId: habit.id, userId: auth.user.id });

    const habitWithStreaks = await getHabitWithStreaks(auth.pb, habit, auth.user.id);
    res.status(201).json(habitWithStreaks);
  } catch (err) {
    log('error', 'Create habit error', { error: err.message });
    res.status(500).json({ message: 'Failed to create habit' });
  }
});

// Get single habit
app.get('/api/habits/:id', async (req, res) => {
  const auth = await authenticateRequest(req);
  if (!auth) {
    return res.status(401).json({ message: 'Unauthorized' });
  }

  try {
    const habit = await auth.pb.collection('habits').getOne(req.params.id);
    
    if (habit.user_id !== auth.user.id) {
      return res.status(403).json({ message: 'Forbidden' });
    }

    if (habit.deleted) {
      return res.status(404).json({ message: 'Habit not found' });
    }

    const habitWithStreaks = await getHabitWithStreaks(auth.pb, habit, auth.user.id);
    res.json(habitWithStreaks);
  } catch (err) {
    if (err.status === 404) {
      return res.status(404).json({ message: 'Habit not found' });
    }
    log('error', 'Get habit error', { error: err.message });
    res.status(500).json({ message: 'Failed to load habit' });
  }
});

// Update habit
app.patch('/api/habits/:id', async (req, res) => {
  const auth = await authenticateRequest(req);
  if (!auth) {
    return res.status(401).json({ message: 'Unauthorized' });
  }

  const { name, description, color } = req.body;

  try {
    const habit = await auth.pb.collection('habits').getOne(req.params.id);
    
    if (habit.user_id !== auth.user.id) {
      return res.status(403).json({ message: 'Forbidden' });
    }

    if (habit.deleted) {
      return res.status(404).json({ message: 'Habit not found' });
    }

    const updates = {};

    if (name !== undefined) {
      if (name.length < 1 || name.length > 80) {
        return res.status(400).json({ message: 'Name must be 1-80 characters' });
      }

      const existing = await auth.pb.collection('habits').getFullList({
        filter: `user_id = "${auth.user.id}" && deleted = false && id != "${req.params.id}"`,
      });

      const nameLower = name.toLowerCase();
      const duplicate = existing.find(h => h.name.toLowerCase() === nameLower);
      if (duplicate) {
        return res.status(409).json({ message: 'A habit with this name already exists' });
      }

      updates.name = name;
    }

    if (description !== undefined) {
      if (description.length > 200) {
        return res.status(400).json({ message: 'Description must be 200 characters or less' });
      }
      updates.description = description;
    }

    if (color !== undefined) {
      const validColors = ['indigo', 'teal', 'amber', 'rose', 'slate', 'forest'];
      if (!validColors.includes(color)) {
        return res.status(400).json({ message: 'Invalid color' });
      }
      updates.color = color;
    }

    const updated = await auth.pb.collection('habits').update(req.params.id, updates);
    
    log('info', 'Habit updated', { habitId: updated.id, userId: auth.user.id });

    const habitWithStreaks = await getHabitWithStreaks(auth.pb, updated, auth.user.id);
    res.json(habitWithStreaks);
  } catch (err) {
    if (err.status === 404) {
      return res.status(404).json({ message: 'Habit not found' });
    }
    log('error', 'Update habit error', { error: err.message });
    res.status(500).json({ message: 'Failed to update habit' });
  }
});

// Delete habit (soft delete)
app.delete('/api/habits/:id', async (req, res) => {
  const auth = await authenticateRequest(req);
  if (!auth) {
    return res.status(401).json({ message: 'Unauthorized' });
  }

  try {
    const habit = await auth.pb.collection('habits').getOne(req.params.id);
    
    if (habit.user_id !== auth.user.id) {
      return res.status(403).json({ message: 'Forbidden' });
    }

    await auth.pb.collection('habits').update(req.params.id, { deleted: true });
    
    log('info', 'Habit deleted', { habitId: req.params.id, userId: auth.user.id });

    res.status(200).json({ success: true });
  } catch (err) {
    if (err.status === 404) {
      return res.status(404).json({ message: 'Habit not found' });
    }
    log('error', 'Delete habit error', { error: err.message });
    res.status(500).json({ message: 'Failed to delete habit' });
  }
});

// Get completions for a habit
app.get('/api/habits/:id/completions', async (req, res) => {
  const auth = await authenticateRequest(req);
  if (!auth) {
    return res.status(401).json({ message: 'Unauthorized' });
  }

  try {
    const habit = await auth.pb.collection('habits').getOne(req.params.id);
    
    if (habit.user_id !== auth.user.id) {
      return res.status(403).json({ message: 'Forbidden' });
    }

    const completions = await auth.pb.collection('completions').getFullList({
      filter: `habit_id = "${req.params.id}" && user_id = "${auth.user.id}"`,
      sort: 'date',
    });

    res.json({
      completions: completions.map(c => c.date),
    });
  } catch (err) {
    if (err.status === 404) {
      return res.status(404).json({ message: 'Habit not found' });
    }
    log('error', 'Get completions error', { error: err.message });
    res.status(500).json({ message: 'Failed to load completions' });
  }
});

// Mark habit complete
app.post('/api/habits/:id/complete', async (req, res) => {
  const auth = await authenticateRequest(req);
  if (!auth) {
    return res.status(401).json({ message: 'Unauthorized' });
  }

  const { date } = req.body;

  if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return res.status(400).json({ message: 'Invalid date format. Use YYYY-MM-DD' });
  }

  const today = getTodayUTC();
  if (date > today) {
    return res.status(400).json({ message: 'Cannot mark completion for a future date' });
  }

  try {
    const habit = await auth.pb.collection('habits').getOne(req.params.id);
    
    if (habit.user_id !== auth.user.id) {
      return res.status(403).json({ message: 'Forbidden' });
    }

    if (habit.deleted) {
      return res.status(404).json({ message: 'Habit not found' });
    }

    const existing = await auth.pb.collection('completions').getFullList({
      filter: `habit_id = "${req.params.id}" && user_id = "${auth.user.id}" && date = "${date}"`,
    });

    if (existing.length > 0) {
      const habitWithStreaks = await getHabitWithStreaks(auth.pb, habit, auth.user.id);
      return res.status(200).json(habitWithStreaks);
    }

    await auth.pb.collection('completions').create({
      habit_id: req.params.id,
      user_id: auth.user.id,
      date,
    });

    log('info', 'Completion added', { habitId: req.params.id, date, userId: auth.user.id });

    const habitWithStreaks = await getHabitWithStreaks(auth.pb, habit, auth.user.id);
    res.status(201).json(habitWithStreaks);
  } catch (err) {
    if (err.status === 404) {
      return res.status(404).json({ message: 'Habit not found' });
    }
    log('error', 'Complete habit error', { error: err.message });
    res.status(500).json({ message: 'Failed to mark completion' });
  }
});

// Unmark habit complete
app.delete('/api/habits/:id/complete', async (req, res) => {
  const auth = await authenticateRequest(req);
  if (!auth) {
    return res.status(401).json({ message: 'Unauthorized' });
  }

  const { date } = req.body;

  if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return res.status(400).json({ message: 'Invalid date format. Use YYYY-MM-DD' });
  }

  try {
    const habit = await auth.pb.collection('habits').getOne(req.params.id);
    
    if (habit.user_id !== auth.user.id) {
      return res.status(403).json({ message: 'Forbidden' });
    }

    const existing = await auth.pb.collection('completions').getFullList({
      filter: `habit_id = "${req.params.id}" && user_id = "${auth.user.id}" && date = "${date}"`,
    });

    if (existing.length > 0) {
      await auth.pb.collection('completions').delete(existing[0].id);
      log('info', 'Completion removed', { habitId: req.params.id, date, userId: auth.user.id });
    }

    res.status(200).json({ success: true });
  } catch (err) {
    if (err.status === 404) {
      return res.status(404).json({ message: 'Habit not found' });
    }
    log('error', 'Uncomplete habit error', { error: err.message });
    res.status(500).json({ message: 'Failed to remove completion' });
  }
});

// Serve static files from frontend build
const frontendDist = join(__dirname, '..', 'frontend', 'dist');
if (existsSync(frontendDist)) {
  app.use(express.static(frontendDist));
  app.get('*', (req, res) => {
    res.sendFile(join(frontendDist, 'index.html'));
  });
}

app.listen(PORT, '0.0.0.0', () => {
  log('info', `Server started on port ${PORT}`, { backendUrl: BACKEND_URL });
});
