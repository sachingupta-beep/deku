#!/usr/bin/env python3
"""Calculator server with expression parser and history management."""

import json
import os
import re
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# In-memory history storage (newest first, max 20 entries)
history = []
MAX_HISTORY = 20


class ExpressionError(Exception):
    """Raised when expression parsing or evaluation fails."""
    pass


class Tokenizer:
    """Tokenize arithmetic expressions."""
    
    TOKEN_PATTERN = re.compile(r'\s*(\d+\.?\d*|\.\d+|[+\-*/()])\s*')
    VALID_CHARS = re.compile(r'^[\d\s+\-*/().]+$')
    
    def __init__(self, expression):
        self.expression = expression
        self.pos = 0
        self.tokens = []
        
    def tokenize(self):
        expr = self.expression.strip()
        if not expr:
            raise ExpressionError("Empty expression")
        
        # Check for invalid characters
        if not self.VALID_CHARS.match(expr):
            raise ExpressionError("Invalid characters in expression")
        
        pos = 0
        while pos < len(expr):
            # Skip whitespace
            while pos < len(expr) and expr[pos].isspace():
                pos += 1
            if pos >= len(expr):
                break
                
            # Match number or operator
            if expr[pos].isdigit() or (expr[pos] == '.' and pos + 1 < len(expr) and expr[pos + 1].isdigit()):
                # Parse number
                start = pos
                has_dot = False
                while pos < len(expr) and (expr[pos].isdigit() or (expr[pos] == '.' and not has_dot)):
                    if expr[pos] == '.':
                        has_dot = True
                    pos += 1
                self.tokens.append(('NUMBER', expr[start:pos]))
            elif expr[pos] in '+-*/()':
                self.tokens.append((expr[pos], expr[pos]))
                pos += 1
            else:
                raise ExpressionError(f"Invalid character: {expr[pos]}")
        
        return self.tokens


class Parser:
    """Recursive descent parser for arithmetic expressions."""
    
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        
    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None
    
    def consume(self, expected_type=None):
        token = self.peek()
        if token is None:
            raise ExpressionError("Unexpected end of expression")
        if expected_type and token[0] != expected_type:
            raise ExpressionError(f"Expected {expected_type}, got {token[0]}")
        self.pos += 1
        return token
    
    def parse(self):
        if not self.tokens:
            raise ExpressionError("Empty expression")
        result = self.parse_expression()
        if self.pos < len(self.tokens):
            raise ExpressionError("Unexpected token after expression")
        return result
    
    def parse_expression(self):
        """Parse addition and subtraction (lowest precedence)."""
        left = self.parse_term()
        
        while self.peek() and self.peek()[0] in ('+', '-'):
            op = self.consume()[0]
            right = self.parse_term()
            if op == '+':
                left = left + right
            else:
                left = left - right
        
        return left
    
    def parse_term(self):
        """Parse multiplication and division (higher precedence)."""
        left = self.parse_factor()
        
        while self.peek() and self.peek()[0] in ('*', '/'):
            op = self.consume()[0]
            right = self.parse_factor()
            if op == '*':
                left = left * right
            else:
                if right == 0:
                    raise ExpressionError("Division by zero")
                left = left / right
        
        return left
    
    def parse_factor(self):
        """Parse unary minus, parentheses, and numbers."""
        token = self.peek()
        
        if token is None:
            raise ExpressionError("Unexpected end of expression")
        
        # Unary minus
        if token[0] == '-':
            self.consume()
            return -self.parse_factor()
        
        # Unary plus (just consume and continue)
        if token[0] == '+':
            self.consume()
            return self.parse_factor()
        
        # Parentheses
        if token[0] == '(':
            self.consume()
            result = self.parse_expression()
            if self.peek() is None or self.peek()[0] != ')':
                raise ExpressionError("Unbalanced parentheses")
            self.consume(')')
            return result
        
        # Number
        if token[0] == 'NUMBER':
            self.consume()
            try:
                return Decimal(token[1])
            except InvalidOperation:
                raise ExpressionError(f"Invalid number: {token[1]}")
        
        # Invalid token in this position
        raise ExpressionError(f"Unexpected token: {token[1]}")


def evaluate_expression(expression):
    """Evaluate an arithmetic expression and return the result."""
    tokenizer = Tokenizer(expression)
    tokens = tokenizer.tokenize()
    
    # Check for empty tokens after tokenization
    if not tokens:
        raise ExpressionError("Empty expression")
    
    # Check for trailing operator
    if tokens[-1][0] in ('+', '-', '*', '/'):
        raise ExpressionError("Trailing operator")
    
    # Check for two operators in a row (except unary minus after open paren or at start)
    for i in range(len(tokens) - 1):
        curr = tokens[i][0]
        next_tok = tokens[i + 1][0]
        
        # Two operators in a row - reject all cases except unary minus after ( or at start
        if curr in ('+', '-', '*', '/') and next_tok in ('+', '-', '*', '/'):
            # Only allow - after ( (handled by checking if curr is '(')
            raise ExpressionError("Two operators in a row")
        
        # Check for operator after open paren (except unary minus)
        if curr == '(' and next_tok in ('+', '*', '/'):
            raise ExpressionError("Invalid expression after parenthesis")
        
        # Check for close paren followed by number or open paren
        if curr == ')' and next_tok in ('NUMBER', '('):
            raise ExpressionError("Missing operator")
        
        # Check for number followed by open paren
        if curr == 'NUMBER' and next_tok == '(':
            raise ExpressionError("Missing operator")
    
    # Check for unbalanced parentheses
    paren_count = 0
    for token in tokens:
        if token[0] == '(':
            paren_count += 1
        elif token[0] == ')':
            paren_count -= 1
        if paren_count < 0:
            raise ExpressionError("Unbalanced parentheses")
    if paren_count != 0:
        raise ExpressionError("Unbalanced parentheses")
    
    parser = Parser(tokens)
    result = parser.parse()
    return result


def format_result(value):
    """Format result: round to 6 decimal places, integers without fractional part."""
    # Round to 6 decimal places using ROUND_HALF_UP
    rounded = value.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
    
    # Normalize to remove trailing zeros
    normalized = rounded.normalize()
    
    # Convert to float for JSON serialization
    float_val = float(normalized)
    
    # If it's an integer, return as int
    if float_val == int(float_val):
        return int(float_val)
    
    return float_val


class CalculatorHandler(BaseHTTPRequestHandler):
    """HTTP request handler for calculator API and static files."""
    
    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")
    
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def send_html(self, content):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(content.encode())
    
    def do_GET(self):
        path = urlparse(self.path).path
        
        if path == '/api/health':
            self.send_json({'ok': True})
        elif path == '/api/history':
            self.send_json({'entries': history})
        elif path == '/':
            self.serve_index()
        else:
            self.send_error(404)
    
    def do_POST(self):
        path = urlparse(self.path).path
        
        if path == '/api/calculate':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode()
            
            try:
                data = json.loads(body)
                expression = data.get('expression', '')
                
                if not isinstance(expression, str):
                    self.send_json({'error': 'Expression must be a string'}, 400)
                    return
                
                result = evaluate_expression(expression)
                formatted_result = format_result(result)
                
                # Add to history (newest first)
                entry = {'expression': expression, 'result': formatted_result}
                history.insert(0, entry)
                
                # Cap at 20 entries
                while len(history) > MAX_HISTORY:
                    history.pop()
                
                self.send_json({'expression': expression, 'result': formatted_result})
                
            except json.JSONDecodeError:
                self.send_json({'error': 'Invalid JSON'}, 400)
            except ExpressionError as e:
                self.send_json({'error': str(e)}, 400)
            except Exception as e:
                self.send_json({'error': str(e)}, 400)
        else:
            self.send_error(404)
    
    def do_DELETE(self):
        path = urlparse(self.path).path
        
        if path == '/api/history':
            history.clear()
            self.send_response(204)
            self.end_headers()
        else:
            self.send_error(404)
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def serve_index(self):
        html = '''<!DOCTYPE html>
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
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: flex-start;
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
            background: #16213e;
            border-radius: 16px;
            padding: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            width: 320px;
        }
        .display {
            background: #0f3460;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            min-height: 80px;
        }
        .expression {
            font-size: 14px;
            color: #888;
            word-break: break-all;
            min-height: 20px;
        }
        .result {
            font-size: 32px;
            font-weight: bold;
            text-align: right;
            word-break: break-all;
        }
        .error {
            background: #e94560;
            color: white;
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 15px;
            display: none;
        }
        .error.visible {
            display: block;
        }
        .keypad {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
        }
        .btn {
            background: #0f3460;
            border: none;
            border-radius: 8px;
            color: #eee;
            font-size: 20px;
            padding: 18px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .btn:hover {
            background: #1a4a7a;
        }
        .btn:active {
            background: #0a2540;
        }
        .btn.operator {
            background: #e94560;
        }
        .btn.operator:hover {
            background: #ff6b8a;
        }
        .btn.equals {
            background: #4ecca3;
            grid-column: span 2;
        }
        .btn.equals:hover {
            background: #6eeec3;
        }
        .btn.clear {
            background: #f39c12;
        }
        .btn.clear:hover {
            background: #f5b041;
        }
        .history-panel {
            background: #16213e;
            border-radius: 16px;
            padding: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            width: 320px;
            max-height: 500px;
            overflow-y: auto;
        }
        .history-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        .history-header h2 {
            font-size: 18px;
        }
        .clear-history {
            background: #e94560;
            border: none;
            border-radius: 6px;
            color: white;
            padding: 8px 12px;
            cursor: pointer;
            font-size: 12px;
        }
        .clear-history:hover {
            background: #ff6b8a;
        }
        .history-list {
            list-style: none;
        }
        .history-item {
            background: #0f3460;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 8px;
        }
        .history-expr {
            font-size: 12px;
            color: #888;
            word-break: break-all;
        }
        .history-result {
            font-size: 18px;
            font-weight: bold;
            text-align: right;
        }
        .empty-history {
            color: #666;
            text-align: center;
            padding: 20px;
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
                <button class="btn" onclick="appendChar('(')">(</button>
                <button class="btn" onclick="appendChar(')')">)</button>
                <button class="btn operator" onclick="appendChar('/')">/</button>
                
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
                <h2>History</h2>
                <button class="clear-history" onclick="clearHistory()">Clear</button>
            </div>
            <ul class="history-list" id="history-list">
                <li class="empty-history">No calculations yet</li>
            </ul>
        </div>
    </div>
    
    <script>
        let currentExpression = '';
        let lastResult = null;
        
        function updateDisplay() {
            document.getElementById('expression').textContent = currentExpression || '';
            if (lastResult !== null) {
                document.getElementById('result').textContent = lastResult;
            } else if (currentExpression === '') {
                document.getElementById('result').textContent = '0';
            }
        }
        
        function showError(message) {
            const errorEl = document.getElementById('error');
            errorEl.textContent = message;
            errorEl.classList.add('visible');
            document.getElementById('result').textContent = '-';
            lastResult = null;
        }
        
        function hideError() {
            document.getElementById('error').classList.remove('visible');
        }
        
        function appendChar(char) {
            hideError();
            currentExpression += char;
            lastResult = null;
            updateDisplay();
        }
        
        function clearAll() {
            currentExpression = '';
            lastResult = null;
            hideError();
            updateDisplay();
        }
        
        async function calculate() {
            if (!currentExpression.trim()) {
                showError('Please enter an expression');
                return;
            }
            
            hideError();
            
            try {
                const response = await fetch('/api/calculate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ expression: currentExpression })
                });
                
                const data = await response.json();
                
                if (!response.ok) {
                    showError(data.error || 'Calculation failed');
                    return;
                }
                
                lastResult = data.result;
                updateDisplay();
                loadHistory();
                
            } catch (err) {
                showError('Network error');
            }
        }
        
        async function loadHistory() {
            try {
                const response = await fetch('/api/history');
                const data = await response.json();
                
                const listEl = document.getElementById('history-list');
                
                if (data.entries.length === 0) {
                    listEl.innerHTML = '<li class="empty-history">No calculations yet</li>';
                    return;
                }
                
                listEl.innerHTML = data.entries.map(entry => `
                    <li class="history-item">
                        <div class="history-expr">${escapeHtml(entry.expression)}</div>
                        <div class="history-result">= ${entry.result}</div>
                    </li>
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
        
        // Load history on page load
        loadHistory();
    </script>
</body>
</html>'''
        self.send_html(html)


def main():
    port = int(os.environ.get('APP_PUBLIC_PORT', 4173))
    server = HTTPServer(('0.0.0.0', port), CalculatorHandler)
    print(f"Calculator server running on http://0.0.0.0:{port}")
    server.serve_forever()


if __name__ == '__main__':
    main()
