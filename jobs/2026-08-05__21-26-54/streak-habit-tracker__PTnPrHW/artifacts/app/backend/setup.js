import PocketBase from 'pocketbase';

const BACKEND_URL = process.env.BACKEND_URL || 'http://pocketbase:8090';
const pb = new PocketBase(BACKEND_URL);

async function setup() {
  console.log('Setting up PocketBase collections...');
  console.log('Backend URL:', BACKEND_URL);

  try {
    // First, try to authenticate as admin
    // If no admin exists, we need to create one first
    try {
      await pb.admins.authWithPassword('admin@ethara.ai', 'admin123456');
      console.log('Admin authenticated');
    } catch (err) {
      console.log('Admin auth failed, trying to create first admin...');
      // Try to create first admin (only works if no admins exist)
      try {
        await pb.admins.create({
          email: 'admin@ethara.ai',
          password: 'admin123456',
          passwordConfirm: 'admin123456',
        });
        console.log('First admin created');
        await pb.admins.authWithPassword('admin@ethara.ai', 'admin123456');
        console.log('Admin authenticated after creation');
      } catch (createErr) {
        console.error('Could not create admin:', createErr.message);
        console.log('Please create an admin manually via the PocketBase UI at', BACKEND_URL + '/_/');
        process.exit(1);
      }
    }

    // Check if habits collection exists
    let habitsExists = false;
    try {
      await pb.collections.getOne('habits');
      habitsExists = true;
      console.log('Habits collection already exists');
    } catch (err) {
      console.log('Habits collection does not exist, creating...');
    }

    if (!habitsExists) {
      await pb.collections.create({
        name: 'habits',
        type: 'base',
        schema: [
          {
            name: 'user_id',
            type: 'relation',
            required: true,
            options: {
              collectionId: '_pb_users_auth_',
              cascadeDelete: false,
              minSelect: null,
              maxSelect: 1,
              displayFields: [],
            },
          },
          {
            name: 'name',
            type: 'text',
            required: true,
            options: {
              min: 1,
              max: 80,
              pattern: '',
            },
          },
          {
            name: 'description',
            type: 'text',
            required: false,
            options: {
              min: null,
              max: 200,
              pattern: '',
            },
          },
          {
            name: 'color',
            type: 'select',
            required: true,
            options: {
              maxSelect: 1,
              values: ['indigo', 'teal', 'amber', 'rose', 'slate', 'forest'],
            },
          },
          {
            name: 'deleted',
            type: 'bool',
            required: false,
            options: {},
          },
        ],
        listRule: '@request.auth.id != "" && user_id = @request.auth.id',
        viewRule: '@request.auth.id != "" && user_id = @request.auth.id',
        createRule: '@request.auth.id != ""',
        updateRule: '@request.auth.id != "" && user_id = @request.auth.id',
        deleteRule: '@request.auth.id != "" && user_id = @request.auth.id',
      });
      console.log('Habits collection created');
    }

    // Check if completions collection exists
    let completionsExists = false;
    try {
      await pb.collections.getOne('completions');
      completionsExists = true;
      console.log('Completions collection already exists');
    } catch (err) {
      console.log('Completions collection does not exist, creating...');
    }

    if (!completionsExists) {
      // Get habits collection ID
      const habitsCollection = await pb.collections.getOne('habits');
      
      await pb.collections.create({
        name: 'completions',
        type: 'base',
        schema: [
          {
            name: 'user_id',
            type: 'relation',
            required: true,
            options: {
              collectionId: '_pb_users_auth_',
              cascadeDelete: false,
              minSelect: null,
              maxSelect: 1,
              displayFields: [],
            },
          },
          {
            name: 'habit_id',
            type: 'relation',
            required: true,
            options: {
              collectionId: habitsCollection.id,
              cascadeDelete: false,
              minSelect: null,
              maxSelect: 1,
              displayFields: [],
            },
          },
          {
            name: 'date',
            type: 'text',
            required: true,
            options: {
              min: 10,
              max: 10,
              pattern: '^\\d{4}-\\d{2}-\\d{2}$',
            },
          },
        ],
        indexes: [
          'CREATE UNIQUE INDEX idx_completion_unique ON completions (user_id, habit_id, date)',
        ],
        listRule: '@request.auth.id != "" && user_id = @request.auth.id',
        viewRule: '@request.auth.id != "" && user_id = @request.auth.id',
        createRule: '@request.auth.id != ""',
        updateRule: null,
        deleteRule: '@request.auth.id != "" && user_id = @request.auth.id',
      });
      console.log('Completions collection created');
    }

    console.log('Setup complete!');
  } catch (err) {
    console.error('Setup error:', err.message);
    if (err.data) {
      console.error('Error data:', JSON.stringify(err.data, null, 2));
    }
    process.exit(1);
  }
}

setup();
