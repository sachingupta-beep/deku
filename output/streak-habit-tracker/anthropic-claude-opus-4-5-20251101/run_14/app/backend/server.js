import express from 'express';
import cors from 'cors';
import PocketBase from 'pocketbase';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.APP_PUBLIC_PORT || 4173;
const BACKEND_URL = process.env.BACKEND_URL || 'http://pocketbase:8090';

app.use(cors());
app.use(express.json());

// Structured logging
function log(level, message, data = {}) {
  console.log(JSON.stringify({
    timestamp: new Date().toISOString(),
    level,
    message,
    ...data,
  }));
}

// Create PocketBase admin client for seeding
const adminPb = new PocketBase(BACKEND_URL);

// Helper to get authenticated user from token
async function getAuthUser(req) {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return null;
  }
  const token = authHeader.slice(7);
  try {
    const pb = new PocketBase(BACKEND_URL);
    pb.authStore.save(token, null);
    // Verify token by fetching auth record
    const authData = await pb.collection('users').authRefresh();
    return { pb, user: authData.record, token: authData.token };
  } catch (err) {
    return null;
  }
}

// Auth middleware
async function requireAuth(req, res, next) {
  const auth = await getAuthUser(req);
  if (!auth) {
    return res.status(401).json({ message: 'Unauthorized' });
  }
  req.auth = auth;
  next();
}

// Calculate streaks for a habit
function calculateStreaks(completions, today) {
  if (!completions || completions.length === 0) {
    return { current_streak: 0, longest_streak: 0 };
  }

  // Sort dates descending
  const dates = [...new Set(completions.map(c => c.date))].sort().reverse();
  
  let currentStreak = 0;
  let longestStreak = 0;
  let streak = 0;
  let expectedDate = today;

  // Check if today is completed for current streak
  const todayCompleted = dates.includes(today);
  
  if (!todayCompleted) {
    currentStreak = 0;
    // Still need to calculate longest streak
    for (let i = 0; i < dates.length; i++) {
      if (i === 0) {
        streak = 1;
      } else {
        const prevDate = new Date(dates[i - 1]);
        const currDate = new Date(dates[i]);
        const diffDays = Math.round((prevDate - currDate) / (1000 * 60 * 60 * 24));
        if (diffDays === 1) {
          streak++;
        } else {
          longestStreak = Math.max(longestStreak, streak);
          streak = 1;
        }
      }
    }
    longestStreak = Math.max(longestStreak, streak);
    return { current_streak: 0, longest_streak: longestStreak };
  }

  // Calculate current streak starting from today
  for (let i = 0; i < dates.length; i++) {
    const date = dates[i];
    if (date === expectedDate) {
      currentStreak++;
      // Move to previous day
      const d = new Date(expectedDate);
      d.setDate(d.getDate() - 1);
      expectedDate = d.toISOString().split('T')[0];
    } else if (i === 0) {
      // First date is not today, current streak is 0
      currentStreak = 0;
      break;
    } else {
      break;
    }
  }

  // Calculate longest streak
  streak = 0;
  for (let i = 0; i < dates.length; i++) {
    if (i === 0) {
      streak = 1;
    } else {
      const prevDate = new Date(dates[i - 1]);
      const currDate = new Date(dates[i]);
      const diffDays = Math.round((prevDate - currDate) / (1000 * 60 * 60 * 24));
      if (diffDays === 1) {
        streak++;
      } else {
        longestStreak = Math.max(longestStreak, streak);
        streak = 1;
      }
    }
  }
  longestStreak = Math.max(longestStreak, streak);

  return { current_streak: currentStreak, longest_streak: longestStreak };
}

// Get today's date in UTC
function getToday() {
  return new Date().toISOString().split('T')[0];
}

// Health check
app.get('/api/health', (req, res) => {
  res.status(200).json({ status: 'ok' });
});

// Login
app.post('/api/auth/login', async (req, res) => {
  try {
    const { email, password } = req.body;
    if (!email || !password) {
      return res.status(400).json({ message: 'Email and password are required' });
    }

    const pb = new PocketBase(BACKEND_URL);
    const authData = await pb.collection('users').authWithPassword(email, password);
    
    log('info', 'User logged in', { email });
    res.json({ access_token: authData.token });
  } catch (err) {
    log('error', 'Login failed', { error: err.message });
    res.status(401).json({ message: 'Invalid credentials' });
  }
});

// Get dashboard
app.get('/api/dashboard', requireAuth, async (req, res) => {
  try {
    const { pb, user } = req.auth;
    const today = getToday();

    // Get all non-deleted habits for user
    const habits = await pb.collection('habits').getFullList({
      filter: `user_id = "${user.id}" && deleted = false`,
    });

    // Get all completions for user
    const completions = await pb.collection('completions').getFullList({
      filter: `user_id = "${user.id}"`,
    });

    // Group completions by habit
    const completionsByHabit = {};
    for (const c of completions) {
      if (!completionsByHabit[c.habit_id]) {
        completionsByHabit[c.habit_id] = [];
      }
      completionsByHabit[c.habit_id].push(c);
    }

    // Build habit list with streaks
    const habitList = habits.map(h => {
      const habitCompletions = completionsByHabit[h.id] || [];
      const { current_streak, longest_streak } = calculateStreaks(habitCompletions, today);
      const completed_today = habitCompletions.some(c => c.date === today);
      
      return {
        id: h.id,
        name: h.name,
        description: h.description,
        color: h.color,
        current_streak,
        longest_streak,
        completed_today,
      };
    });

    const habitsWithActiveStreak = habitList.filter(h => h.current_streak >= 1).length;

    res.json({
      total_habits: habits.length,
      total_completions: completions.length,
      habits_with_active_streak: habitsWithActiveStreak,
      habits: habitList,
    });
  } catch (err) {
    log('error', 'Dashboard error', { error: err.message });
    res.status(500).json({ message: 'Failed to load dashboard' });
  }
});

// Get all habits
app.get('/api/habits', requireAuth, async (req, res) => {
  try {
    const { pb, user } = req.auth;
    const today = getToday();

    const habits = await pb.collection('habits').getFullList({
      filter: `user_id = "${user.id}" && deleted = false`,
    });

    const completions = await pb.collection('completions').getFullList({
      filter: `user_id = "${user.id}"`,
    });

    const completionsByHabit = {};
    for (const c of completions) {
      if (!completionsByHabit[c.habit_id]) {
        completionsByHabit[c.habit_id] = [];
      }
      completionsByHabit[c.habit_id].push(c);
    }

    const habitList = habits.map(h => {
      const habitCompletions = completionsByHabit[h.id] || [];
      const { current_streak, longest_streak } = calculateStreaks(habitCompletions, today);
      const completed_today = habitCompletions.some(c => c.date === today);
      
      return {
        id: h.id,
        name: h.name,
        description: h.description,
        color: h.color,
        current_streak,
        longest_streak,
        completed_today,
      };
    });

    res.json(habitList);
  } catch (err) {
    log('error', 'Get habits error', { error: err.message });
    res.status(500).json({ message: 'Failed to load habits' });
  }
});

// Create habit
app.post('/api/habits', requireAuth, async (req, res) => {
  try {
    const { pb, user } = req.auth;
    const { name, color, description } = req.body;

    // Validate name
    if (!name || name.length < 1 || name.length > 80) {
      return res.status(400).json({ message: 'Name must be 1-80 characters' });
    }

    // Validate color
    const validColors = ['indigo', 'teal', 'amber', 'rose', 'slate', 'forest'];
    if (!color || !validColors.includes(color)) {
      return res.status(400).json({ message: 'Invalid color' });
    }

    // Validate description
    if (description && description.length > 200) {
      return res.status(400).json({ message: 'Description must be at most 200 characters' });
    }

    // Check for duplicate name (case-insensitive)
    const existing = await pb.collection('habits').getFullList({
      filter: `user_id = "${user.id}" && deleted = false`,
    });
    
    const nameLower = name.toLowerCase();
    const duplicate = existing.find(h => h.name.toLowerCase() === nameLower);
    if (duplicate) {
      return res.status(409).json({ message: 'A habit with this name already exists' });
    }

    const habit = await pb.collection('habits').create({
      user_id: user.id,
      name,
      color,
      description: description || '',
      deleted: false,
    });

    log('info', 'Habit created', { habitId: habit.id, userId: user.id });

    res.status(201).json({
      id: habit.id,
      name: habit.name,
      description: habit.description,
      color: habit.color,
      current_streak: 0,
      longest_streak: 0,
      completed_today: false,
    });
  } catch (err) {
    log('error', 'Create habit error', { error: err.message });
    res.status(500).json({ message: 'Failed to create habit' });
  }
});

// Get single habit
app.get('/api/habits/:id', requireAuth, async (req, res) => {
  try {
    const { pb, user } = req.auth;
    const { id } = req.params;
    const today = getToday();

    const habit = await pb.collection('habits').getOne(id);
    
    if (habit.user_id !== user.id) {
      return res.status(403).json({ message: 'Forbidden' });
    }

    if (habit.deleted) {
      return res.status(404).json({ message: 'Habit not found' });
    }

    const completions = await pb.collection('completions').getFullList({
      filter: `habit_id = "${id}" && user_id = "${user.id}"`,
    });

    const { current_streak, longest_streak } = calculateStreaks(completions, today);
    const completed_today = completions.some(c => c.date === today);

    res.json({
      id: habit.id,
      name: habit.name,
      description: habit.description,
      color: habit.color,
      current_streak,
      longest_streak,
      completed_today,
    });
  } catch (err) {
    if (err.status === 404) {
      return res.status(404).json({ message: 'Habit not found' });
    }
    log('error', 'Get habit error', { error: err.message });
    res.status(500).json({ message: 'Failed to load habit' });
  }
});

// Update habit
app.patch('/api/habits/:id', requireAuth, async (req, res) => {
  try {
    const { pb, user } = req.auth;
    const { id } = req.params;
    const { name, color, description } = req.body;
    const today = getToday();

    const habit = await pb.collection('habits').getOne(id);
    
    if (habit.user_id !== user.id) {
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
      
      // Check for duplicate name (case-insensitive), excluding current habit
      const existing = await pb.collection('habits').getFullList({
        filter: `user_id = "${user.id}" && deleted = false && id != "${id}"`,
      });
      
      const nameLower = name.toLowerCase();
      const duplicate = existing.find(h => h.name.toLowerCase() === nameLower);
      if (duplicate) {
        return res.status(409).json({ message: 'A habit with this name already exists' });
      }
      
      updates.name = name;
    }

    if (color !== undefined) {
      const validColors = ['indigo', 'teal', 'amber', 'rose', 'slate', 'forest'];
      if (!validColors.includes(color)) {
        return res.status(400).json({ message: 'Invalid color' });
      }
      updates.color = color;
    }

    if (description !== undefined) {
      if (description.length > 200) {
        return res.status(400).json({ message: 'Description must be at most 200 characters' });
      }
      updates.description = description;
    }

    const updated = await pb.collection('habits').update(id, updates);

    const completions = await pb.collection('completions').getFullList({
      filter: `habit_id = "${id}" && user_id = "${user.id}"`,
    });

    const { current_streak, longest_streak } = calculateStreaks(completions, today);
    const completed_today = completions.some(c => c.date === today);

    log('info', 'Habit updated', { habitId: id, userId: user.id });

    res.json({
      id: updated.id,
      name: updated.name,
      description: updated.description,
      color: updated.color,
      current_streak,
      longest_streak,
      completed_today,
    });
  } catch (err) {
    if (err.status === 404) {
      return res.status(404).json({ message: 'Habit not found' });
    }
    log('error', 'Update habit error', { error: err.message });
    res.status(500).json({ message: 'Failed to update habit' });
  }
});

// Delete habit (soft delete)
app.delete('/api/habits/:id', requireAuth, async (req, res) => {
  try {
    const { pb, user } = req.auth;
    const { id } = req.params;

    const habit = await pb.collection('habits').getOne(id);
    
    if (habit.user_id !== user.id) {
      return res.status(403).json({ message: 'Forbidden' });
    }

    await pb.collection('habits').update(id, { deleted: true });

    log('info', 'Habit deleted', { habitId: id, userId: user.id });

    res.status(204).send();
  } catch (err) {
    if (err.status === 404) {
      return res.status(404).json({ message: 'Habit not found' });
    }
    log('error', 'Delete habit error', { error: err.message });
    res.status(500).json({ message: 'Failed to delete habit' });
  }
});

// Complete habit
app.post('/api/habits/:id/complete', requireAuth, async (req, res) => {
  try {
    const { pb, user } = req.auth;
    const { id } = req.params;
    const { date } = req.body;
    const today = getToday();

    // Validate date format
    if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      return res.status(400).json({ message: 'Invalid date format. Use YYYY-MM-DD' });
    }

    // Check if date is in the future
    if (date > today) {
      return res.status(400).json({ message: 'Cannot mark future dates as complete' });
    }

    const habit = await pb.collection('habits').getOne(id);
    
    if (habit.user_id !== user.id) {
      return res.status(403).json({ message: 'Forbidden' });
    }

    if (habit.deleted) {
      return res.status(404).json({ message: 'Habit not found' });
    }

    // Check if already completed
    const existing = await pb.collection('completions').getFullList({
      filter: `habit_id = "${id}" && user_id = "${user.id}" && date = "${date}"`,
    });

    if (existing.length > 0) {
      // Already completed, return 200 (no-op)
      return res.status(200).json({ message: 'Already completed' });
    }

    const completion = await pb.collection('completions').create({
      habit_id: id,
      user_id: user.id,
      date,
    });

    log('info', 'Habit completed', { habitId: id, userId: user.id, date });

    res.status(201).json({
      id: completion.id,
      habit_id: completion.habit_id,
      user_id: completion.user_id,
      date: completion.date,
    });
  } catch (err) {
    if (err.status === 404) {
      return res.status(404).json({ message: 'Habit not found' });
    }
    log('error', 'Complete habit error', { error: err.message });
    res.status(500).json({ message: 'Failed to complete habit' });
  }
});

// Uncomplete habit
app.delete('/api/habits/:id/complete', requireAuth, async (req, res) => {
  try {
    const { pb, user } = req.auth;
    const { id } = req.params;
    const { date } = req.body;

    // Validate date format
    if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      return res.status(400).json({ message: 'Invalid date format. Use YYYY-MM-DD' });
    }

    const habit = await pb.collection('habits').getOne(id);
    
    if (habit.user_id !== user.id) {
      return res.status(403).json({ message: 'Forbidden' });
    }

    // Find and delete completion
    const existing = await pb.collection('completions').getFullList({
      filter: `habit_id = "${id}" && user_id = "${user.id}" && date = "${date}"`,
    });

    if (existing.length === 0) {
      // Not completed, return 200 (no-op)
      return res.status(200).json({ message: 'Not completed' });
    }

    await pb.collection('completions').delete(existing[0].id);

    log('info', 'Habit uncompleted', { habitId: id, userId: user.id, date });

    res.status(204).send();
  } catch (err) {
    if (err.status === 404) {
      return res.status(404).json({ message: 'Habit not found' });
    }
    log('error', 'Uncomplete habit error', { error: err.message });
    res.status(500).json({ message: 'Failed to uncomplete habit' });
  }
});

// Get completions for a habit
app.get('/api/habits/:id/completions', requireAuth, async (req, res) => {
  try {
    const { pb, user } = req.auth;
    const { id } = req.params;

    const habit = await pb.collection('habits').getOne(id);
    
    if (habit.user_id !== user.id) {
      return res.status(403).json({ message: 'Forbidden' });
    }

    const completions = await pb.collection('completions').getFullList({
      filter: `habit_id = "${id}" && user_id = "${user.id}"`,
      sort: '-date',
    });

    res.json(completions.map(c => ({
      id: c.id,
      habit_id: c.habit_id,
      user_id: c.user_id,
      date: c.date,
      created: c.created,
    })));
  } catch (err) {
    if (err.status === 404) {
      return res.status(404).json({ message: 'Habit not found' });
    }
    log('error', 'Get completions error', { error: err.message });
    res.status(500).json({ message: 'Failed to load completions' });
  }
});

// Serve static files from frontend build
const frontendPath = path.join(__dirname, '../frontend/dist');
app.use(express.static(frontendPath));

// SPA fallback - Express 5 syntax
app.get('/{*path}', (req, res) => {
  res.sendFile(path.join(frontendPath, 'index.html'));
});

// Seed database
async function seedDatabase() {
  try {
    log('info', 'Checking if seeding is needed...');
    
    const pb = new PocketBase(BACKEND_URL);
    
    // Try to authenticate as demo user to check if they exist
    let demoUser;
    let userPb;
    try {
      const authData = await pb.collection('users').authWithPassword('demo@ethara.ai', 'deku-demo-pw-2026');
      demoUser = authData.record;
      userPb = pb;
      log('info', 'Demo user exists, checking if habits need to be seeded');
      
      // Check if habits already exist
      const existingHabits = await userPb.collection('habits').getFullList({
        filter: `user_id = "${demoUser.id}"`,
      });
      
      if (existingHabits.length > 0) {
        log('info', 'Habits already exist, skipping seed');
        return;
      }
    } catch (err) {
      // User doesn't exist, create them
      log('info', 'Demo user does not exist, creating...');
      try {
        demoUser = await pb.collection('users').create({
          email: 'demo@ethara.ai',
          password: 'deku-demo-pw-2026',
          passwordConfirm: 'deku-demo-pw-2026',
          emailVisibility: true,
        });
        log('info', 'Demo user created', { userId: demoUser.id });
        
        // Authenticate as the new user
        const authData = await pb.collection('users').authWithPassword('demo@ethara.ai', 'deku-demo-pw-2026');
        demoUser = authData.record;
        userPb = pb;
      } catch (createErr) {
        log('error', 'Failed to create demo user', { error: createErr.message });
        return;
      }
    }

    const today = getToday();
    
    // Helper to get date N days ago
    function daysAgo(n) {
      const d = new Date(today);
      d.setDate(d.getDate() - n);
      return d.toISOString().split('T')[0];
    }

    // Create habits
    const meditateHabit = await userPb.collection('habits').create({
      user_id: demoUser.id,
      name: 'Meditate',
      color: 'indigo',
      description: '',
      deleted: false,
    });
    log('info', 'Created Meditate habit', { habitId: meditateHabit.id });

    const readHabit = await userPb.collection('habits').create({
      user_id: demoUser.id,
      name: 'Read 20 minutes',
      color: 'teal',
      description: '',
      deleted: false,
    });
    log('info', 'Created Read 20 minutes habit', { habitId: readHabit.id });

    const sodaHabit = await userPb.collection('habits').create({
      user_id: demoUser.id,
      name: 'No soda',
      color: 'amber',
      description: '',
      deleted: false,
    });
    log('info', 'Created No soda habit', { habitId: sodaHabit.id });

    // Create completions for Meditate: current_streak = 5 (today + 4 previous days)
    for (let i = 0; i < 5; i++) {
      await userPb.collection('completions').create({
        habit_id: meditateHabit.id,
        user_id: demoUser.id,
        date: daysAgo(i),
      });
    }
    log('info', 'Created Meditate completions (5 day streak)');

    // Create completions for Read 20 minutes: current_streak = 0, longest_streak >= 3
    // 3 consecutive days earlier this month, nothing today
    for (let i = 10; i < 13; i++) {
      await userPb.collection('completions').create({
        habit_id: readHabit.id,
        user_id: demoUser.id,
        date: daysAgo(i),
      });
    }
    log('info', 'Created Read 20 minutes completions (3 day streak earlier)');

    // Create completions for No soda: current_streak = 1 (today only, gap yesterday)
    await userPb.collection('completions').create({
      habit_id: sodaHabit.id,
      user_id: demoUser.id,
      date: today,
    });
    log('info', 'Created No soda completions (1 day streak)');

    log('info', 'Database seeding complete');
  } catch (err) {
    log('error', 'Seeding error', { error: err.message, details: err.data });
  }
}

// Start server
app.listen(PORT, '0.0.0.0', async () => {
  log('info', `Server started on port ${PORT}`);
  log('info', `PocketBase URL: ${BACKEND_URL}`);
  
  // Wait a bit for PocketBase to be ready, then seed
  setTimeout(seedDatabase, 2000);
});
