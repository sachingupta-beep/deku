#!/usr/bin/env python3
"""Calculator web server with history."""

import json
import os
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

# In-memory history storage (newest first, max 20 entries)
history = []
MAX_HISTORY = 20


class CalculatorError(Exception):
    """Custom exception for calculator errors."""
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
            raise CalculatorError("Empty expression")
        
        # Check for invalid characters
        if not self.VALID_CHARS.match(expr):
            raise CalculatorError("Invalid characters in expression")
        
        pos = 0
        while pos < len(expr):
            # Skip whitespace
            while pos < len(expr) and expr[pos].isspace():
                pos += 1
            if pos >= len(expr):
                break
                
            # Match number
            if expr[pos].isdigit() or (expr[pos] == '.' and pos + 1 < len(expr) and expr[pos + 1].isdigit()):
                start = pos
                has_dot = False
                while pos < len(expr) and (expr[pos].isdigit() or (expr[pos] == '.' and not has_dot)):
                    if expr[pos] == '.':
                        has_dot = True
                    pos += 1
                self.tokens.append(('NUMBER', expr[start:pos]))
            # Match operator or parenthesis
            elif expr[pos] in '+-*/()':
                self.tokens.append((expr[pos], expr[pos]))
                pos += 1
            else:
                raise CalculatorError(f"Invalid character: {expr[pos]}")
        
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
    
    def consume(self):
        token = self.peek()
        self.pos += 1
        return token
    
    def parse(self):
        if not self.tokens:
            raise CalculatorError("Empty expression")
        result = self.parse_expression(allow_unary=True)
        if self.peek() is not None:
            raise CalculatorError("Unexpected token after expression")
        return result
    
    def parse_expression(self, allow_unary=False):
        """Parse addition and subtraction (lowest precedence)."""
        left = self.parse_term(allow_unary=allow_unary)
        
        while self.peek() and self.peek()[0] in ('+', '-'):
            op = self.consume()[0]
            right = self.parse_term(allow_unary=False)
            if op == '+':
                left = left + right
            else:
                left = left - right
        
        return left
    
    def parse_term(self, allow_unary=False):
        """Parse multiplication and division (higher precedence)."""
        left = self.parse_factor(allow_unary=allow_unary)
        
        while self.peek() and self.peek()[0] in ('*', '/'):
            op = self.consume()[0]
            right = self.parse_factor(allow_unary=False)
            if op == '*':
                left = left * right
            else:
                if right == 0:
                    raise CalculatorError("Division by zero")
                left = left / right
        
        return left
    
    def parse_factor(self, allow_unary=False):
        """Parse unary minus and atoms."""
        token = self.peek()
        
        if token is None:
            raise CalculatorError("Unexpected end of expression")
        
        # Unary minus - only allowed at start or after open paren
        if token[0] == '-':
            if not allow_unary:
                raise CalculatorError("Two operators in a row")
            self.consume()
            return -self.parse_factor(allow_unary=False)
        
        # Reject unary plus after binary operator
        if token[0] == '+':
            if not allow_unary:
                raise CalculatorError("Two operators in a row")
            self.consume()
            return self.parse_factor(allow_unary=False)
        
        return self.parse_atom()
    
    def parse_atom(self):
        """Parse numbers and parenthesized expressions."""
        token = self.peek()
        
        if token is None:
            raise CalculatorError("Unexpected end of expression")
        
        if token[0] == 'NUMBER':
            self.consume()
            try:
                return Decimal(token[1])
            except InvalidOperation:
                raise CalculatorError(f"Invalid number: {token[1]}")
        
        if token[0] == '(':
            self.consume()
            result = self.parse_expression(allow_unary=True)
            if self.peek() is None or self.peek()[0] != ')':
                raise CalculatorError("Unbalanced parentheses")
            self.consume()
            return result
        
        raise CalculatorError(f"Unexpected token: {token[1]}")


def evaluate(expression):
    """Evaluate an arithmetic expression and return the result."""
    tokenizer = Tokenizer(expression)
    tokens = tokenizer.tokenize()
    parser = Parser(tokens)
    result = parser.parse()
    return result


def format_result(value):
    """Format result: round to 6 decimal places, remove trailing zeros."""
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
    """HTTP request handler for the calculator API."""
    
    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")
    
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def send_error_json(self, message, status=400):
        self.send_json({'error': message}, status)
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        if self.path == '/api/health':
            self.send_json({'ok': True})
        elif self.path == '/api/history':
            self.send_json({'entries': history})
        elif self.path == '/':
            self.serve_file('/app/index.html', 'text/html')
        elif self.path.endswith('.css'):
            self.serve_file(f'/app{self.path}', 'text/css')
        elif self.path.endswith('.js'):
            self.serve_file(f'/app{self.path}', 'application/javascript')
        else:
            self.send_error(404)
    
    def serve_file(self, filepath, content_type):
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404)
    
    def do_POST(self):
        if self.path == '/api/calculate':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode()
            
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self.send_error_json('Invalid JSON')
                return
            
            expression = data.get('expression', '')
            
            try:
                result = evaluate(expression)
                formatted = format_result(result)
                
                # Add to history (newest first)
                global history
                entry = {'expression': expression, 'result': formatted}
                history.insert(0, entry)
                
                # Cap at 20 entries
                if len(history) > MAX_HISTORY:
                    history = history[:MAX_HISTORY]
                
                self.send_json({'expression': expression, 'result': formatted})
            except CalculatorError as e:
                self.send_error_json(str(e))
        else:
            self.send_error(404)
    
    def do_DELETE(self):
        if self.path == '/api/history':
            global history
            history = []
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
        else:
            self.send_error(404)


def main():
    port = int(os.environ.get('APP_PUBLIC_PORT', 4173))
    server = HTTPServer(('0.0.0.0', port), CalculatorHandler)
    print(f"Calculator server running on port {port}")
    server.serve_forever()


if __name__ == '__main__':
    main()
