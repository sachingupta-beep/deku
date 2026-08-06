#!/usr/bin/env python3
"""Calculator web server with history."""

import json
import os
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

# Server-side history storage (newest first, max 20)
history = []
MAX_HISTORY = 20


class ExpressionError(Exception):
    """Raised when expression is invalid."""
    pass


class Tokenizer:
    """Tokenize arithmetic expressions."""
    
    TOKEN_PATTERN = re.compile(r'\s*(\d+\.?\d*|\.\d+|[+\-*/()])\s*')
    VALID_CHARS = re.compile(r'^[\d\s+\-*/().]+$')
    
    def __init__(self, expression):
        self.expression = expression.strip()
        self.pos = 0
        self.tokens = []
        
    def tokenize(self):
        if not self.expression:
            raise ExpressionError("Empty expression")
        
        if not self.VALID_CHARS.match(self.expression):
            raise ExpressionError("Invalid characters in expression")
        
        remaining = self.expression
        while remaining.strip():
            remaining = remaining.lstrip()
            match = self.TOKEN_PATTERN.match(remaining)
            if not match:
                raise ExpressionError(f"Invalid token at: {remaining[:10]}")
            token = match.group(1)
            self.tokens.append(token)
            remaining = remaining[match.end()-match.start():]
            remaining = remaining.lstrip()
        
        if not self.tokens:
            raise ExpressionError("Empty expression")
            
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
        result = self.parse_expression()
        if self.pos < len(self.tokens):
            raise ExpressionError(f"Unexpected token: {self.peek()}")
        return result
    
    def parse_expression(self):
        """Parse addition and subtraction (lowest precedence)."""
        left = self.parse_term()
        
        while self.peek() in ('+', '-'):
            op = self.consume()
            right = self.parse_term()
            if op == '+':
                left = left + right
            else:
                left = left - right
        
        return left
    
    def parse_term(self):
        """Parse multiplication and division (higher precedence)."""
        left = self.parse_factor()
        
        while self.peek() in ('*', '/'):
            op = self.consume()
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
        
        if token == '-':
            self.consume()
            return -self.parse_factor()
        
        if token == '+':
            self.consume()
            return self.parse_factor()
        
        if token == '(':
            self.consume()
            result = self.parse_expression()
            if self.peek() != ')':
                raise ExpressionError("Unbalanced parentheses")
            self.consume()
            return result
        
        if token == ')':
            raise ExpressionError("Unexpected closing parenthesis")
        
        if token is None:
            raise ExpressionError("Unexpected end of expression")
        
        # Must be a number
        try:
            self.consume()
            return Decimal(token)
        except InvalidOperation:
            raise ExpressionError(f"Invalid number: {token}")


def evaluate_expression(expression):
    """Evaluate an arithmetic expression safely."""
    tokenizer = Tokenizer(expression)
    tokens = tokenizer.tokenize()
    
    # Validate token sequence
    validate_token_sequence(tokens)
    
    parser = Parser(tokens)
    result = parser.parse()
    
    # Round to 6 decimal places using half-up rounding
    result = result.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
    
    # Normalize to remove trailing zeros
    result = result.normalize()
    
    # Convert to float for JSON serialization
    float_result = float(result)
    
    # If it's an integer, return as int
    if float_result == int(float_result):
        return int(float_result)
    
    return float_result


def validate_token_sequence(tokens):
    """Validate that token sequence is well-formed."""
    if not tokens:
        raise ExpressionError("Empty expression")
    
    operators = {'+', '-', '*', '/'}
    binary_operators = {'*', '/'}  # These cannot appear at start
    
    # Check for trailing operator (except unary +/-)
    last = tokens[-1]
    if last in operators:
        raise ExpressionError("Expression ends with operator")
    
    # Check for two binary operators in a row, or invalid sequences
    prev = None
    paren_depth = 0
    
    for i, token in enumerate(tokens):
        if token == '(':
            paren_depth += 1
        elif token == ')':
            paren_depth -= 1
            if paren_depth < 0:
                raise ExpressionError("Unbalanced parentheses")
        
        if prev is not None:
            # Two operators in a row - only allow unary minus after '(' or at start
            # Unary minus is only valid: leading or after open paren
            if prev in operators and token in operators:
                # Only allow - after ( for unary minus
                raise ExpressionError("Two operators in a row")
            
            # Operator after open paren must be - (unary minus only)
            if prev == '(' and token in {'+', '*', '/'}:
                raise ExpressionError("Invalid operator after opening parenthesis")
            
            # Close paren followed by number or open paren without operator
            if prev == ')' and (token not in operators and token != ')'):
                raise ExpressionError("Missing operator after closing parenthesis")
            
            # Number followed by open paren without operator
            if prev not in operators and prev not in '()' and token == '(':
                raise ExpressionError("Missing operator before opening parenthesis")
            
            # Close paren followed by open paren without operator
            if prev == ')' and token == '(':
                raise ExpressionError("Missing operator between parentheses")
        
        # First token cannot be * or / (but + and - are allowed as unary)
        # Actually, only - is allowed as unary at start per spec
        if i == 0 and token in {'+', '*', '/'}:
            raise ExpressionError("Expression starts with invalid operator")
        
        prev = token
    
    if paren_depth != 0:
        raise ExpressionError("Unbalanced parentheses")


class CalculatorHandler(BaseHTTPRequestHandler):
    """HTTP request handler for calculator API."""
    
    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")
    
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def send_error_json(self, message, status=400):
        self.send_json({'error': message}, status)
    
    def do_GET(self):
        if self.path == '/api/health':
            self.send_json({'ok': True})
        
        elif self.path == '/api/history':
            self.send_json({'entries': history})
        
        elif self.path == '/' or self.path == '/index.html':
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
            
            if not isinstance(expression, str):
                self.send_error_json('Expression must be a string')
                return
            
            try:
                result = evaluate_expression(expression)
            except ExpressionError as e:
                self.send_error_json(str(e))
                return
            except Exception as e:
                self.send_error_json(f'Evaluation error: {str(e)}')
                return
            
            # Add to history (newest first)
            entry = {'expression': expression, 'result': result}
            history.insert(0, entry)
            
            # Cap at 20 entries
            while len(history) > MAX_HISTORY:
                history.pop()
            
            self.send_json({'expression': expression, 'result': result})
        
        else:
            self.send_error(404)
    
    def do_DELETE(self):
        if self.path == '/api/history':
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


def main():
    port = int(os.environ.get('APP_PUBLIC_PORT', 4173))
    server = HTTPServer(('0.0.0.0', port), CalculatorHandler)
    print(f"Calculator server running on http://0.0.0.0:{port}")
    server.serve_forever()


if __name__ == '__main__':
    main()
