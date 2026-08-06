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

async function ensureCollections() {
  try {
    await pb.admins.authWithPassword(
      process.env.PB_ADMIN_EMAIL || 'admin@ethara.ai',
      process.env.PB_ADMIN_PASSWORD || 'adminpassword123'
    );
  } catch (err) {
    log('Admin auth failed, trying to create collections without admin', { error: err.message });
  }

  try {
    await pb.collections.getOne('habits');
    log('habits collection exists');
  } catch (err) {
    if (err.status === 404) {
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
      } catch (createErr) {
        log('Failed to create habits collection', { error: createErr.message });
      }
    }
  }

  try {
    await pb.collections.getOne('completions');
    log('completions collection exists');
  } catch (err) {
    if (err.status === 404) {
      log('Creating completions collection');
      try {
        await pb.collections.create({
          name: 'completions',
          type: 'base',
          schema: [
            { name: 'user_id', type: 'relation', required: true, options: { collectionId: '_pb_users_auth_', maxSelect: 1 } },
            { name: 'habit_id', type: 'relation', required: true, options: { collectionId: 'habits', maxSelect: 1 } },
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
      } catch (createErr) {
        log('Failed to create completions collection', { error: createErr.message });
      }
    }
  }
}

async function seed() {
  log('Starting seed process', { backendUrl: BACKEND_URL });

  const email = 'demo@ethara.ai';
  const password = 'deku-demo-pw-2026';

  let user;
  
  try {
    const authData = await pb.collection('users').authWithPassword(email, password);
    user = authData.record;
    log('Demo user already exists', { userId: user.id });
  } catch (err) {
    log('Creating demo user');
    try {
      user = await pb.collection('users').create({
        email,
        password,
        passwordConfirm: password,
        emailVisibility: true,
      });
      log('Demo user created', { userId: user.id });
      
      await pb.collection('users').authWithPassword(email, password);
    } catch (createErr) {
      log('Failed to create user', { error: createErr.message });
      throw createErr;
    }
  }

  const habits = await pb.collection('habits').getFullList({
    filter: `user_id = "${user.id}"`,
  });

  if (habits.length > 0) {
    log('Habits already exist, skipping seed', { count: habits.length });
    return;
  }

  log('Creating seed habits');

  const meditateHabit = await pb.collection('habits').create({
    user_id: user.id,
    name: 'Meditate',
    description: '10 minutes of mindfulness',
    color: 'indigo',
    deleted: false,
  });

  const readHabit = await pb.collection('habits').create({
    user_id: user.id,
    name: 'Read 20 minutes',
    description: 'Read a book for at least 20 minutes',
    color: 'teal',
    deleted: false,
  });

  const sodaHabit = await pb.collection('habits').create({
    user_id: user.id,
    name: 'No soda',
    description: 'Avoid sugary drinks',
    color: 'amber',
    deleted: false,
  });

  log('Creating seed completions');

  const today = getTodayUTC();

  for (let i = 0; i < 5; i++) {
    const date = getDateOffset(-i);
    await pb.collection('completions').create({
      user_id: user.id,
      habit_id: meditateHabit.id,
      date,
    });
  }
  log('Meditate completions created (5 day streak including today)');

  for (let i = 10; i < 13; i++) {
    const date = getDateOffset(-i);
    await pb.collection('completions').create({
      user_id: user.id,
      habit_id: readHabit.id,
      date,
    });
  }
  log('Read completions created (3 day streak earlier this month, not today)');

  await pb.collection('completions').create({
    user_id: user.id,
    habit_id: sodaHabit.id,
    date: today,
  });
  log('No soda completion created (today only, gap yesterday)');

  log('Seed completed successfully');
}

seed().catch(err => {
  console.error('Seed failed:', err);
  process.exit(1);
});
