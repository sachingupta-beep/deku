# Deku Calculator

A single-page calculator web application with history.

## Login

No login required. This application does not use authentication.

## Usage

Open the application in a browser to use the calculator. Enter arithmetic expressions using the keypad or keyboard, and press equals to evaluate. History is displayed on the right panel and persists across page reloads.

## API Endpoints

- `GET /api/health` - Health check
- `POST /api/calculate` - Evaluate an expression
- `GET /api/history` - Get calculation history
- `DELETE /api/history` - Clear history
