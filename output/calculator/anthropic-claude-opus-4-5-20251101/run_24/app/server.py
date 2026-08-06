#!/usr/bin/env python3
"""
Deku Calculator - A single-page calculator with history.
No external dependencies, uses Python standard library only.
"""

import json
import os
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

# Server-side history storage (in-memory, max 20 entries)
history = []
MAX_HISTORY = 20


class ArithmeticParser:
    """
    Recursive descent parser for arithmetic expressions.
    Supports: +, -, *, /, parentheses, unary minus, decimals.
    Unary minus only allowed at start or after open parenthesis.
    """
    
    def __init__(self, expression):
        self.expression = expression
        self.pos = 0
        self.tokens = self._tokenize()
        self.token_pos = 0
    
    def _tokenize(self):
        """Tokenize the expression into numbers and operators."""
        tokens = []
        expr = self.expression.replace(' ', '')
        
        if not expr:
            raise ValueError("Empty expression")
        
        i = 0
        while i < len(expr):
            char = expr[i]
            
            if char in '+-*/()':
                tokens.append(char)
                i += 1
            elif char.isdigit() or char == '.':
                # Parse number
                num_str = ''
                has_dot = False
                while i < len(expr) and (expr[i].isdigit() or expr[i] == '.'):
                    if expr[i] == '.':
                        if has_dot:
                            raise ValueError("Invalid number format")
                        has_dot = True
                    num_str += expr[i]
                    i += 1
                if num_str == '.' or num_str.endswith('.') and len(num_str) == 1:
                    raise ValueError("Invalid number format")
                tokens.append(('NUM', num_str))
            else:
                raise ValueError(f"Invalid character: {char}")
        
        # Validate token sequence
        self._validate_tokens(tokens)
        
        return tokens
    
    def _validate_tokens(self, tokens):
        """Validate token sequence for malformed expressions."""
        if not tokens:
            raise ValueError("Empty expression")
        
        # Check for trailing operator
        last = tokens[-1]
        if last in ('+', '-', '*', '/', '('):
            raise ValueError("Malformed expression")
        
        # Check for two operators in a row (except unary minus after '(' or at start)
        for i, token in enumerate(tokens):
            if token in ('+', '-', '*', '/'):
                # Check what comes next
                if i + 1 < len(tokens):
                    next_token = tokens[i + 1]
                    # After a binary operator, only ( or number is allowed
                    # Exception: unary minus is allowed after ( or at start
                    if next_token in ('+', '*', '/', ')'):
                        raise ValueError("Malformed expression")
                    # Two operators in a row: only allow - after ( or at start
                    if next_token == '-':
                        # Check if current position allows unary minus
                        # Unary minus allowed: at start, or after (
                        if i > 0 and tokens[i] != '(':
                            raise ValueError("Malformed expression")
            
            # Check for ( followed by operator other than -
            if token == '(':
                if i + 1 < len(tokens):
                    next_token = tokens[i + 1]
                    if next_token in ('+', '*', '/', ')'):
                        raise ValueError("Malformed expression")
        
        # Check for unbalanced parentheses (basic check)
        paren_count = 0
        for token in tokens:
            if token == '(':
                paren_count += 1
            elif token == ')':
                paren_count -= 1
                if paren_count < 0:
                    raise ValueError("Unbalanced parentheses")
        if paren_count != 0:
            raise ValueError("Unbalanced parentheses")
    
    def _current_token(self):
        if self.token_pos < len(self.tokens):
            return self.tokens[self.token_pos]
        return None
    
    def _consume(self, expected=None):
        token = self._current_token()
        if expected is not None and token != expected:
            raise ValueError(f"Expected {expected}, got {token}")
        self.token_pos += 1
        return token
    
    def parse(self):
        """Parse and evaluate the expression."""
        if not self.tokens:
            raise ValueError("Empty expression")
        result = self._parse_expression()
        if self._current_token() is not None:
            raise ValueError("Unexpected token at end of expression")
        return result
    
    def _parse_expression(self):
        """Parse addition and subtraction (lowest precedence)."""
        left = self._parse_term()
        
        while self._current_token() in ('+', '-'):
            op = self._consume()
            right = self._parse_term()
            if op == '+':
                left = left + right
            else:
                left = left - right
        
        return left
    
    def _parse_term(self):
        """Parse multiplication and division (higher precedence)."""
        left = self._parse_factor()
        
        while self._current_token() in ('*', '/'):
            op = self._consume()
            right = self._parse_factor()
            if op == '*':
                left = left * right
            else:
                if right == 0:
                    raise ValueError("Division by zero")
                left = left / right
        
        return left
    
    def _parse_factor(self):
        """Parse unary minus, parentheses, and numbers."""
        token = self._current_token()
        
        # Handle unary minus (only at start or after open paren - validated in tokenize)
        if token == '-':
            self._consume()
            return -self._parse_factor()
        
        # Handle parentheses
        if token == '(':
            self._consume()
            result = self._parse_expression()
            if self._current_token() != ')':
                raise ValueError("Unbalanced parentheses")
            self._consume()
            return result
        
        # Handle numbers
        if isinstance(token, tuple) and token[0] == 'NUM':
            self._consume()
            return Decimal(token[1])
        
        if token == ')':
            raise ValueError("Unexpected closing parenthesis")
        
        if token == '+':
            raise ValueError("Malformed expression")
        
        raise ValueError("Expected number or expression")


def evaluate_expression(expression):
    """
    Evaluate an arithmetic expression and return the result.
    Returns (result, None) on success or (None, error_message) on failure.
    """
    if not expression or not expression.strip():
        return None, "Empty expression"
    
    try:
        parser = ArithmeticParser(expression)
        result = parser.parse()
        
        # Round to 6 decimal places using ROUND_HALF_UP
        result = result.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
        
        # Normalize to remove trailing zeros
        result = result.normalize()
        
        # Convert to float for JSON serialization
        result_float = float(result)
        
        # If it's an integer, return as int
        if result_float == int(result_float):
            return int(result_float), None
        
        return result_float, None
        
    except (ValueError, InvalidOperation) as e:
        return None, str(e)
    except Exception as e:
        return None, f"Evaluation error: {str(e)}"


class CalculatorHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the calculator API and frontend."""
    
    def log_message(self, format, *args):
        """Log to stdout."""
        print(f"{self.address_string()} - {format % args}")
    
    def _send_json(self, data, status=200):
        """Send a JSON response."""
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)
    
    def _send_html(self, html, status=200):
        """Send an HTML response."""
        body = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)
    
    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/api/health':
            self._send_json({'ok': True})
        
        elif self.path == '/api/history':
            self._send_json({'entries': list(history)})
        
        elif self.path == '/':
            self._send_html(get_html_page())
        
        else:
            self._send_json({'error': 'Not found'}, 404)
    
    def do_POST(self):
        """Handle POST requests."""
        if self.path == '/api/calculate':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._send_json({'error': 'Invalid JSON'}, 400)
                return
            
            expression = data.get('expression', '')
            result, error = evaluate_expression(expression)
            
            if error:
                self._send_json({'error': error}, 400)
                return
            
            # Add to history (newest first, max 20)
            entry = {'expression': expression, 'result': result}
            history.insert(0, entry)
            if len(history) > MAX_HISTORY:
                history.pop()
            
            self._send_json({'expression': expression, 'result': result})
        
        else:
            self._send_json({'error': 'Not found'}, 404)
    
    def do_DELETE(self):
        """Handle DELETE requests."""
        if self.path == '/api/history':
            history.clear()
            self.send_response(204)
            self.end_headers()
        else:
            self._send_json({'error': 'Not found'}, 404)


def get_html_page():
    """Return the calculator HTML page."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Deku Calculator</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
            justify-content: center;
            max-width: 800px;
        }
        .calculator {
            background: #0f0f23;
            border-radius: 20px;
            padding: 25px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
            width: 320px;
        }
        .display {
            background: #1a1a3e;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            min-height: 100px;
        }
        .expression {
            color: #8888aa;
            font-size: 16px;
            min-height: 24px;
            word-break: break-all;
        }
        .result {
            color: #fff;
            font-size: 36px;
            font-weight: 600;
            text-align: right;
            min-height: 44px;
            word-break: break-all;
        }
        .error {
            background: #ff4444;
            color: white;
            padding: 10px 15px;
            border-radius: 8px;
            margin-bottom: 15px;
            font-size: 14px;
            display: none;
        }
        .error.visible {
            display: block;
        }
        .keypad {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
        }
        .btn {
            background: #1a1a3e;
            border: none;
            border-radius: 12px;
            color: #fff;
            font-size: 20px;
            padding: 18px;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .btn:hover {
            background: #2a2a5e;
            transform: translateY(-2px);
        }
        .btn:active {
            transform: translateY(0);
        }
        .btn.operator {
            background: #4a4a8e;
        }
        .btn.operator:hover {
            background: #5a5a9e;
        }
        .btn.equals {
            background: #00c853;
            grid-column: span 2;
        }
        .btn.equals:hover {
            background: #00e676;
        }
        .btn.clear {
            background: #ff5252;
        }
        .btn.clear:hover {
            background: #ff6b6b;
        }
        .history-panel {
            background: #0f0f23;
            border-radius: 20px;
            padding: 25px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
            width: 320px;
            max-height: 500px;
            display: flex;
            flex-direction: column;
        }
        .history-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        .history-title {
            color: #fff;
            font-size: 18px;
            font-weight: 600;
        }
        .clear-history {
            background: #ff5252;
            border: none;
            border-radius: 8px;
            color: #fff;
            padding: 8px 15px;
            cursor: pointer;
            font-size: 14px;
            transition: background 0.15s ease;
        }
        .clear-history:hover {
            background: #ff6b6b;
        }
        .history-list {
            flex: 1;
            overflow-y: auto;
            padding-right: 5px;
        }
        .history-item {
            background: #1a1a3e;
            border-radius: 10px;
            padding: 12px 15px;
            margin-bottom: 10px;
        }
        .history-expr {
            color: #8888aa;
            font-size: 14px;
            word-break: break-all;
        }
        .history-result {
            color: #00c853;
            font-size: 20px;
            font-weight: 600;
            text-align: right;
        }
        .empty-history {
            color: #555;
            text-align: center;
            padding: 40px 20px;
        }
        @media (max-width: 700px) {
            .container {
                flex-direction: column;
                align-items: center;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="calculator">
            <div class="display">
                <div class="expression" id="expression"></div>
                <div class="result" id="result">0</div>
            </div>
            <div class="error" id="error"></div>
            <div class="keypad">
                <button class="btn clear" onclick="clearAll()">C</button>
                <button class="btn operator" onclick="appendChar('(')">(</button>
                <button class="btn operator" onclick="appendChar(')')">)</button>
                <button class="btn operator" onclick="appendChar('/')">÷</button>
                
                <button class="btn" onclick="appendChar('7')">7</button>
                <button class="btn" onclick="appendChar('8')">8</button>
                <button class="btn" onclick="appendChar('9')">9</button>
                <button class="btn operator" onclick="appendChar('*')">×</button>
                
                <button class="btn" onclick="appendChar('4')">4</button>
                <button class="btn" onclick="appendChar('5')">5</button>
                <button class="btn" onclick="appendChar('6')">6</button>
                <button class="btn operator" onclick="appendChar('-')">−</button>
                
                <button class="btn" onclick="appendChar('1')">1</button>
                <button class="btn" onclick="appendChar('2')">2</button>
                <button class="btn" onclick="appendChar('3')">3</button>
                <button class="btn operator" onclick="appendChar('+')">+</button>
                
                <button class="btn" onclick="appendChar('0')">0</button>
                <button class="btn" onclick="appendChar('.')">.</button>
                <button class="btn equals" onclick="calculate()">=</button>
            </div>
        </div>
        
        <div class="history-panel">
            <div class="history-header">
                <span class="history-title">History</span>
                <button class="clear-history" onclick="clearHistory()">Clear</button>
            </div>
            <div class="history-list" id="historyList">
                <div class="empty-history">No calculations yet</div>
            </div>
        </div>
    </div>
    
    <script>
        let expression = '';
        let hasResult = false;
        
        function updateDisplay() {
            document.getElementById('expression').textContent = expression || '';
            hideError();
        }
        
        function showError(message) {
            const errorEl = document.getElementById('error');
            errorEl.textContent = message;
            errorEl.classList.add('visible');
            document.getElementById('result').textContent = '-';
        }
        
        function hideError() {
            document.getElementById('error').classList.remove('visible');
        }
        
        function appendChar(char) {
            if (hasResult) {
                expression = '';
                hasResult = false;
            }
            expression += char;
            updateDisplay();
        }
        
        function clearAll() {
            expression = '';
            hasResult = false;
            document.getElementById('result').textContent = '0';
            updateDisplay();
        }
        
        async function calculate() {
            if (!expression.trim()) {
                showError('Please enter an expression');
                return;
            }
            
            try {
                const response = await fetch('/api/calculate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ expression: expression })
                });
                
                const data = await response.json();
                
                if (!response.ok) {
                    showError(data.error || 'Calculation error');
                    return;
                }
                
                document.getElementById('result').textContent = data.result;
                hasResult = true;
                hideError();
                loadHistory();
            } catch (err) {
                showError('Network error');
            }
        }
        
        async function loadHistory() {
            try {
                const response = await fetch('/api/history');
                const data = await response.json();
                
                const listEl = document.getElementById('historyList');
                
                if (data.entries.length === 0) {
                    listEl.innerHTML = '<div class="empty-history">No calculations yet</div>';
                    return;
                }
                
                listEl.innerHTML = data.entries.map(entry => `
                    <div class="history-item">
                        <div class="history-expr">${escapeHtml(entry.expression)}</div>
                        <div class="history-result">= ${entry.result}</div>
                    </div>
                `).join('');
            } catch (err) {
                console.error('Failed to load history:', err);
            }
        }
        
        async function clearHistory() {
            try {
                await fetch('/api/history', { method: 'DELETE' });
                loadHistory();
            } catch (err) {
                console.error('Failed to clear history:', err);
            }
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // Handle keyboard input
        document.addEventListener('keydown', (e) => {
            if (e.key >= '0' && e.key <= '9') appendChar(e.key);
            else if (e.key === '+' || e.key === '-' || e.key === '*' || e.key === '/') appendChar(e.key);
            else if (e.key === '(' || e.key === ')') appendChar(e.key);
            else if (e.key === '.') appendChar('.');
            else if (e.key === 'Enter' || e.key === '=') calculate();
            else if (e.key === 'Escape' || e.key === 'c' || e.key === 'C') clearAll();
            else if (e.key === 'Backspace') {
                expression = expression.slice(0, -1);
                updateDisplay();
            }
        });
        
        // Load history on page load
        loadHistory();
    </script>
</body>
</html>
'''


def main():
    port = int(os.environ.get('APP_PUBLIC_PORT', 4173))
    server = HTTPServer(('0.0.0.0', port), CalculatorHandler)
    print(f"Deku Calculator running on http://0.0.0.0:{port}")
    server.serve_forever()


if __name__ == '__main__':
    main()
