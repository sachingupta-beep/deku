#!/usr/bin/env python3
"""
Deku Calculator - A single-page calculator with history.
Serves both the web UI and JSON API on a single port.
"""

import json
import os
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

# Server-side history storage (in-memory, max 20 entries)
history = []
MAX_HISTORY = 20


class ExpressionError(Exception):
    """Custom exception for expression parsing/evaluation errors."""
    pass


class Tokenizer:
    """Tokenizes arithmetic expressions into numbers, operators, and parentheses."""
    
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
            
            # Try to match a token
            match = self.TOKEN_PATTERN.match(expr, pos)
            if not match:
                raise ExpressionError(f"Invalid token at position {pos}")
            
            token = match.group(1)
            self.tokens.append(token)
            pos = match.end()
        
        if not self.tokens:
            raise ExpressionError("Empty expression")
        
        return self.tokens


class Parser:
    """
    Recursive descent parser for arithmetic expressions.
    Grammar:
        expr   -> term (('+' | '-') term)*
        term   -> factor (('*' | '/') factor)*
        factor -> '-' factor | primary
        primary -> NUMBER | '(' expr ')'
    """
    
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
    
    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None
    
    def consume(self):
        token = self.peek()
        self.pos += 1
        return token
    
    def parse(self):
        result = self.expr()
        if self.pos < len(self.tokens):
            raise ExpressionError(f"Unexpected token: {self.peek()}")
        return result
    
    def expr(self):
        """Parse addition and subtraction (lowest precedence)."""
        left = self.term()
        
        while self.peek() in ('+', '-'):
            op = self.consume()
            right = self.term()
            if op == '+':
                left = left + right
            else:
                left = left - right
        
        return left
    
    def term(self):
        """Parse multiplication and division (higher precedence)."""
        left = self.factor()
        
        while self.peek() in ('*', '/'):
            op = self.consume()
            right = self.factor()
            if op == '*':
                left = left * right
            else:
                if right == 0:
                    raise ExpressionError("Division by zero")
                left = left / right
        
        return left
    
    def factor(self):
        """Parse unary minus and primary expressions."""
        if self.peek() == '-':
            self.consume()
            return -self.factor()
        return self.primary()
    
    def primary(self):
        """Parse numbers and parenthesized expressions."""
        token = self.peek()
        
        if token is None:
            raise ExpressionError("Unexpected end of expression")
        
        if token == '(':
            self.consume()
            result = self.expr()
            if self.peek() != ')':
                raise ExpressionError("Unbalanced parentheses: missing ')'")
            self.consume()
            return result
        
        if token == ')':
            raise ExpressionError("Unbalanced parentheses: unexpected ')'")
        
        if token in ('+', '-', '*', '/'):
            raise ExpressionError(f"Unexpected operator: {token}")
        
        # Must be a number
        try:
            self.consume()
            return Decimal(token)
        except InvalidOperation:
            raise ExpressionError(f"Invalid number: {token}")


def evaluate_expression(expression):
    """
    Evaluate an arithmetic expression and return the result.
    Returns a properly formatted number (integer if whole, else up to 6 decimal places).
    """
    tokenizer = Tokenizer(expression)
    tokens = tokenizer.tokenize()
    
    parser = Parser(tokens)
    result = parser.parse()
    
    # Round to 6 decimal places using ROUND_HALF_UP
    result = result.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
    
    # Normalize to remove trailing zeros
    result = result.normalize()
    
    # Convert to appropriate Python type
    if result == result.to_integral_value():
        return int(result)
    else:
        return float(result)


def add_to_history(expression, result):
    """Add a calculation to history, maintaining max 20 entries."""
    global history
    history.insert(0, {"expression": expression, "result": result})
    if len(history) > MAX_HISTORY:
        history = history[:MAX_HISTORY]


def clear_history():
    """Clear all history entries."""
    global history
    history = []


def get_history():
    """Get all history entries."""
    return history.copy()


# HTML template for the calculator page
HTML_PAGE = '''<!DOCTYPE html>
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
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            padding: 20px;
        }
        .container {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            max-width: 800px;
            width: 100%;
            justify-content: center;
        }
        .calculator {
            background: #2d2d2d;
            border-radius: 20px;
            padding: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            width: 320px;
        }
        .display {
            background: #1a1a1a;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            min-height: 100px;
        }
        .expression {
            color: #888;
            font-size: 18px;
            min-height: 24px;
            word-break: break-all;
        }
        .result {
            color: #fff;
            font-size: 36px;
            font-weight: bold;
            text-align: right;
            min-height: 44px;
            word-break: break-all;
        }
        .error {
            color: #ff6b6b;
            font-size: 14px;
            margin-top: 10px;
            min-height: 20px;
        }
        .keypad {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
        }
        .btn {
            background: #404040;
            border: none;
            border-radius: 10px;
            color: #fff;
            font-size: 24px;
            padding: 20px;
            cursor: pointer;
            transition: background 0.2s, transform 0.1s;
        }
        .btn:hover {
            background: #505050;
        }
        .btn:active {
            transform: scale(0.95);
        }
        .btn-operator {
            background: #ff9500;
        }
        .btn-operator:hover {
            background: #ffaa33;
        }
        .btn-equals {
            background: #34c759;
        }
        .btn-equals:hover {
            background: #4cd964;
        }
        .btn-clear {
            background: #ff3b30;
        }
        .btn-clear:hover {
            background: #ff5c54;
        }
        .btn-paren {
            background: #5856d6;
        }
        .btn-paren:hover {
            background: #7674e0;
        }
        .history-panel {
            background: #2d2d2d;
            border-radius: 20px;
            padding: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
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
            font-size: 20px;
            font-weight: bold;
        }
        .btn-clear-history {
            background: #ff3b30;
            border: none;
            border-radius: 8px;
            color: #fff;
            font-size: 14px;
            padding: 8px 16px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .btn-clear-history:hover {
            background: #ff5c54;
        }
        .history-list {
            flex: 1;
            overflow-y: auto;
            scrollbar-width: thin;
            scrollbar-color: #555 #2d2d2d;
        }
        .history-list::-webkit-scrollbar {
            width: 8px;
        }
        .history-list::-webkit-scrollbar-track {
            background: #2d2d2d;
        }
        .history-list::-webkit-scrollbar-thumb {
            background: #555;
            border-radius: 4px;
        }
        .history-item {
            background: #404040;
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 10px;
        }
        .history-expr {
            color: #888;
            font-size: 14px;
            word-break: break-all;
        }
        .history-result {
            color: #fff;
            font-size: 20px;
            font-weight: bold;
            text-align: right;
        }
        .empty-history {
            color: #666;
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
                <div class="error" id="error"></div>
            </div>
            <div class="keypad">
                <button class="btn btn-clear" onclick="clearDisplay()">C</button>
                <button class="btn btn-paren" onclick="appendChar('(')">(</button>
                <button class="btn btn-paren" onclick="appendChar(')')">)</button>
                <button class="btn btn-operator" onclick="appendChar('/')">/</button>
                
                <button class="btn" onclick="appendChar('7')">7</button>
                <button class="btn" onclick="appendChar('8')">8</button>
                <button class="btn" onclick="appendChar('9')">9</button>
                <button class="btn btn-operator" onclick="appendChar('*')">*</button>
                
                <button class="btn" onclick="appendChar('4')">4</button>
                <button class="btn" onclick="appendChar('5')">5</button>
                <button class="btn" onclick="appendChar('6')">6</button>
                <button class="btn btn-operator" onclick="appendChar('-')">-</button>
                
                <button class="btn" onclick="appendChar('1')">1</button>
                <button class="btn" onclick="appendChar('2')">2</button>
                <button class="btn" onclick="appendChar('3')">3</button>
                <button class="btn btn-operator" onclick="appendChar('+')">+</button>
                
                <button class="btn" onclick="appendChar('0')">0</button>
                <button class="btn" onclick="appendChar('.')">.</button>
                <button class="btn" onclick="backspace()">⌫</button>
                <button class="btn btn-equals" onclick="calculate()">=</button>
            </div>
        </div>
        
        <div class="history-panel">
            <div class="history-header">
                <span class="history-title">History</span>
                <button class="btn-clear-history" onclick="clearHistory()">Clear</button>
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
            document.getElementById('error').textContent = '';
        }
        
        function appendChar(char) {
            if (hasResult) {
                // If we just got a result and user types a number or (, start fresh
                if (/[0-9(]/.test(char)) {
                    expression = '';
                }
                hasResult = false;
            }
            expression += char;
            updateDisplay();
            document.getElementById('result').textContent = expression;
        }
        
        function clearDisplay() {
            expression = '';
            hasResult = false;
            document.getElementById('expression').textContent = '';
            document.getElementById('result').textContent = '0';
            document.getElementById('error').textContent = '';
        }
        
        function backspace() {
            if (hasResult) {
                clearDisplay();
                return;
            }
            expression = expression.slice(0, -1);
            updateDisplay();
            document.getElementById('result').textContent = expression || '0';
        }
        
        async function calculate() {
            if (!expression.trim()) {
                return;
            }
            
            try {
                const response = await fetch('/api/calculate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ expression: expression })
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    document.getElementById('expression').textContent = expression + ' =';
                    document.getElementById('result').textContent = data.result;
                    document.getElementById('error').textContent = '';
                    expression = String(data.result);
                    hasResult = true;
                    loadHistory();
                } else {
                    document.getElementById('expression').textContent = expression;
                    document.getElementById('result').textContent = '-';
                    document.getElementById('error').textContent = data.error || 'Error';
                    hasResult = false;
                }
            } catch (err) {
                document.getElementById('result').textContent = '-';
                document.getElementById('error').textContent = 'Network error';
            }
        }
        
        async function loadHistory() {
            try {
                const response = await fetch('/api/history');
                const data = await response.json();
                
                const historyList = document.getElementById('historyList');
                
                if (data.entries && data.entries.length > 0) {
                    historyList.innerHTML = data.entries.map(entry => `
                        <div class="history-item">
                            <div class="history-expr">${escapeHtml(entry.expression)}</div>
                            <div class="history-result">= ${entry.result}</div>
                        </div>
                    `).join('');
                } else {
                    historyList.innerHTML = '<div class="empty-history">No calculations yet</div>';
                }
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
        
        // Keyboard support
        document.addEventListener('keydown', function(e) {
            if (e.key >= '0' && e.key <= '9') {
                appendChar(e.key);
            } else if (e.key === '+' || e.key === '-' || e.key === '*' || e.key === '/') {
                appendChar(e.key);
            } else if (e.key === '(' || e.key === ')') {
                appendChar(e.key);
            } else if (e.key === '.') {
                appendChar('.');
            } else if (e.key === 'Enter' || e.key === '=') {
                e.preventDefault();
                calculate();
            } else if (e.key === 'Backspace') {
                backspace();
            } else if (e.key === 'Escape' || e.key === 'c' || e.key === 'C') {
                clearDisplay();
            }
        });
    </script>
</body>
</html>
'''


class CalculatorHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the calculator application."""
    
    def log_message(self, format, *args):
        """Log to stdout."""
        print(f"{self.address_string()} - {format % args}")
    
    def send_json(self, data, status=200):
        """Send a JSON response."""
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)
    
    def send_html(self, html, status=200):
        """Send an HTML response."""
        body = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)
    
    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/':
            self.send_html(HTML_PAGE)
        elif self.path == '/api/health':
            self.send_json({"ok": True})
        elif self.path == '/api/history':
            self.send_json({"entries": get_history()})
        else:
            self.send_json({"error": "Not found"}, 404)
    
    def do_POST(self):
        """Handle POST requests."""
        if self.path == '/api/calculate':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            
            try:
                data = json.loads(body)
                expression = data.get('expression', '')
                
                if not isinstance(expression, str):
                    self.send_json({"error": "Expression must be a string"}, 400)
                    return
                
                result = evaluate_expression(expression)
                add_to_history(expression, result)
                self.send_json({"expression": expression, "result": result})
                
            except json.JSONDecodeError:
                self.send_json({"error": "Invalid JSON"}, 400)
            except ExpressionError as e:
                self.send_json({"error": str(e)}, 400)
            except Exception as e:
                self.send_json({"error": str(e)}, 400)
        else:
            self.send_json({"error": "Not found"}, 404)
    
    def do_DELETE(self):
        """Handle DELETE requests."""
        if self.path == '/api/history':
            clear_history()
            self.send_response(204)
            self.end_headers()
        else:
            self.send_json({"error": "Not found"}, 404)


def main():
    port = int(os.environ.get('APP_PUBLIC_PORT', 4173))
    server = HTTPServer(('0.0.0.0', port), CalculatorHandler)
    print(f"Deku Calculator running on http://0.0.0.0:{port}")
    server.serve_forever()


if __name__ == '__main__':
    main()
