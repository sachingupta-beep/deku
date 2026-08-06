import PocketBase from 'pocketbase';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8090';
const pb = new PocketBase(BACKEND_URL);
pb.autoCancellation(false);

function log(message, data = {}) {
  console.log(JSON.stringify({
    timestamp: new Date().toISOString(),
    level: 'info',
    message,
    ...data
  }));
}

function getTodayUTC() {
  return new Date().toISOString().split('T')[0];
}

function getDateOffset(days) {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().split('T')[0];
}

async function setup() {
  log('Starting setup', { backendUrl: BACKEND_URL });

  // First, try to create admin if needed
  let adminToken = null;
  
  try {
    // Try to auth with existing admin
    const adminAuth = await pb.admins.authWithPassword('admin@ethara.ai', 'adminpassword123456');
    adminToken = adminAuth.token;
    log('Admin auth successful');
  } catch (err) {
    log('Admin auth failed, trying to create admin', { error: err.message });
    
    try {
      // Create first admin
      const response = await fetch(`${BACKEND_URL}/api/admins`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: 'admin@ethara.ai',
          password: 'adminpassword123456',
          passwordConfirm: 'adminpassword123456',
        }),
      });
      
      if (response.ok) {
        log('Admin created');
        const adminAuth = await pb.admins.authWithPassword('admin@ethara.ai', 'adminpassword123456');
        adminToken = adminAuth.token;
      } else {
        const errData = await response.json();
        log('Failed to create admin', { error: errData });
      }
    } catch (createErr) {
      log('Admin creation error', { error: createErr.message });
    }
  }

  if (!adminToken) {
    log('No admin token, will try to proceed without admin');
  }

  // Check if habits collection exists
  let habitsExists = false;
  let completionsExists = false;
  
  try {
    const collections = await pb.collections.getFullList();
    habitsExists = collections.some(c => c.name === 'habits');
    completionsExists = collections.some(c => c.name === 'completions');
    log('Collections check', { habitsExists, completionsExists });
  } catch (err) {
    log('Failed to list collections', { error: err.message });
  }

  // Create habits collection if needed
  if (!habitsExists) {
    log('Creating habits collection');
    try {
      await pb.collections.create({
        name: 'habits',
        type: 'base',
        schema: [
          { name: 'user_id', type: 'relation', required: true, options: { collectionId: '_pb_users_auth_', maxSelect: 1 } },
          { name: 'name', type: 'text', required: true, options: { min: 1, max: 80 } },
          { name: 'description', type: 'text', required: false, options: { max: 200 } },
          { name: 'color', type: 'select', required: true, options: { values: ['indigo', 'teal', 'amber', 'rose', 'slate', 'forest'] } },
          { name: 'deleted', type: 'bool', required: false },
        ],
        listRule: '@request.auth.id != "" && user_id = @request.auth.id',
        viewRule: '@request.auth.id != "" && user_id = @request.auth.id',
        createRule: '@request.auth.id != ""',
        updateRule: '@request.auth.id != "" && user_id = @request.auth.id',
        deleteRule: '@request.auth.id != "" && user_id = @request.auth.id',
      });
      log('habits collection created');
    } catch (err) {
      log('Failed to create habits collection', { error: err.message, details: err.data });
    }
  }

  // Create completions collection if needed
  if (!completionsExists) {
    log('Creating completions collection');
    try {
      // First get the habits collection ID
      const habitsCol = await pb.collections.getOne('habits');
      
      await pb.collections.create({
        name: 'completions',
        type: 'base',
        schema: [
          { name: 'user_id', type: 'relation', required: true, options: { collectionId: '_pb_users_auth_', maxSelect: 1 } },
          { name: 'habit_id', type: 'relation', required: true, options: { collectionId: habitsCol.id, maxSelect: 1 } },
          { name: 'date', type: 'text', required: true },
        ],
        indexes: [
          'CREATE UNIQUE INDEX idx_completion_unique ON completions (user_id, habit_id, date)',
        ],
        listRule: '@request.auth.id != "" && user_id = @request.auth.id',
        viewRule: '@request.auth.id != "" && user_id = @request.auth.id',
        createRule: '@request.auth.id != ""',
        updateRule: '@request.auth.id != "" && user_id = @request.auth.id',
        deleteRule: '@request.auth.id != "" && user_id = @request.auth.id',
      });
      log('completions collection created');
    } catch (err) {
      log('Failed to create completions collection', { error: err.message, details: err.data });
    }
  }

  // Now seed the demo user and data
  const email = 'demo@ethara.ai';
  const password = 'deku-demo-pw-2026';

  let user;
  
  // Try to login as demo user
  try {
    const authData = await pb.collection('users').authWithPassword(email, password);
    user = authData.record;
    log('Demo user already exists', { userId: user.id });
  } catch (err) {
    log('Demo user does not exist, creating');
    try {
      user = await pb.collection('users').create({
        email,
        password,
        passwordConfirm: password,
        emailVisibility: true,
      });
      log('Demo user created', { userId: user.id });
      
      // Auth as the new user
      await pb.collection('users').authWithPassword(email, password);
    } catch (createErr) {
      log('Failed to create demo user', { error: createErr.message, details: createErr.data });
      throw createErr;
    }
  }

  // Check if habits already exist for this user
  try {
    const existingHabits = await pb.collection('habits').getFullList({
      filter: `user_id = "${user.id}"`,
    });

    if (existingHabits.length > 0) {
      log('Habits already exist for demo user, skipping seed', { count: existingHabits.length });
      return;
    }
  } catch (err) {
    log('Error checking existing habits', { error: err.message });
  }

  log('Creating seed habits');

  try {
    const meditateHabit = await pb.collection('habits').create({
      user_id: user.id,
      name: 'Meditate',
      description: '10 minutes of mindfulness',
      color: 'indigo',
      deleted: false,
    });
    log('Created Meditate habit', { id: meditateHabit.id });

    const readHabit = await pb.collection('habits').create({
      user_id: user.id,
      name: 'Read 20 minutes',
      description: 'Read a book for at least 20 minutes',
      color: 'teal',
      deleted: false,
    });
    log('Created Read habit', { id: readHabit.id });

    const sodaHabit = await pb.collection('habits').create({
      user_id: user.id,
      name: 'No soda',
      description: 'Avoid sugary drinks',
      color: 'amber',
      deleted: false,
    });
    log('Created No soda habit', { id: sodaHabit.id });

    log('Creating seed completions');

    const today = getTodayUTC();

    // Meditate: 5 day streak including today
    for (let i = 0; i < 5; i++) {
      const date = getDateOffset(-i);
      await pb.collection('completions').create({
        user_id: user.id,
        habit_id: meditateHabit.id,
        date,
      });
    }
    log('Meditate completions created (5 day streak including today)');

    // Read: 3 day streak earlier, not today (longest_streak >= 3, current_streak = 0)
    for (let i = 10; i < 13; i++) {
      const date = getDateOffset(-i);
      await pb.collection('completions').create({
        user_id: user.id,
        habit_id: readHabit.id,
        date,
      });
    }
    log('Read completions created (3 day streak earlier this month, not today)');

    // No soda: today only, gap yesterday (current_streak = 1)
    await pb.collection('completions').create({
      user_id: user.id,
      habit_id: sodaHabit.id,
      date: today,
    });
    log('No soda completion created (today only, gap yesterday)');

    log('Seed completed successfully');
  } catch (err) {
    log('Error creating seed data', { error: err.message, details: err.data });
    throw err;
  }
}

setup().catch(err => {
  console.error('Setup failed:', err);
  process.exit(1);
});
