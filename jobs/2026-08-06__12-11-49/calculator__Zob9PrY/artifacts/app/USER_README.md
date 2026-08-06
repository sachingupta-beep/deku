# Deku Calculator

A single-page calculator web application with history.

## Features

- Arithmetic calculator with +, -, *, / operators
- Parentheses support with proper precedence
- Unary minus support
- Server-side history (max 20 entries, newest first)
- Clear history functionality
- Keyboard support

## Running

```bash
./start.sh
```

The server will start on the port specified by `APP_PUBLIC_PORT` (default: 4173).

## API Endpoints

- `GET /api/health` - Health check
- `POST /api/calculate` - Evaluate expression
- `GET /api/history` - Get calculation history
- `DELETE /api/history` - Clear history

## Login

No login required. This is a single-user application with no authentication.
