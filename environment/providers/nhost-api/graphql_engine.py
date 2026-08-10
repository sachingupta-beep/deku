"""A small Hasura-flavoured GraphQL engine for the Nhost mock service.

Scope is deliberately the subset Hasura exposes over a Postgres schema, which is
what an agent talking to Nhost actually sends:

* queries and mutations, named or shorthand, with `$variables`
* root fields `<table>`, `<table>_by_pk`, `<table>_aggregate`,
  `insert_<table>_one`, `update_<table>_by_pk`, `delete_<table>_by_pk`
* arguments `where`, `order_by`, `limit`, `offset`, `distinct_on`
* boolean expressions with `_and` / `_or` / `_not`, the comparison operators and
  relationship traversal
* object and array relationships in the selection set, nested arbitrarily deep
* aggregate selections (`count`, `sum`, `avg`, `min`, `max`)
* aliases

Everything is evaluated against plain lists of dicts supplied by the caller, so
this module has no dependency on the store or on FastAPI.
"""

import re

_PUNCT = set("{}()[]:,$!=")
_NAME_RE = re.compile(r"[_A-Za-z][_0-9A-Za-z]*")
_NUMBER_RE = re.compile(r"-?\d+(\.\d+)?([eE][+-]?\d+)?")


class GraphQLError(Exception):
    """Raised for a parse or validation failure; carries a Hasura error code."""

    def __init__(self, message, code="validation-failed"):
        super().__init__(message)
        self.message = message
        self.code = code


# ---------------------------------------------------------------------------
# Lexer + parser
# ---------------------------------------------------------------------------

def _tokenize(source):
    tokens, i, n = [], 0, len(source)
    while i < n:
        ch = source[i]
        if ch in " \t\n\r,﻿":
            i += 1
            continue
        if ch == "#":
            while i < n and source[i] != "\n":
                i += 1
            continue
        if ch == '"':
            if source.startswith('"""', i):
                end = source.find('"""', i + 3)
                if end == -1:
                    raise GraphQLError("unterminated block string")
                tokens.append(("STRING", source[i + 3:end]))
                i = end + 3
                continue
            j, buf = i + 1, []
            while j < n and source[j] != '"':
                if source[j] == "\\" and j + 1 < n:
                    buf.append({"n": "\n", "t": "\t", '"': '"',
                                "\\": "\\"}.get(source[j + 1], source[j + 1]))
                    j += 2
                    continue
                buf.append(source[j])
                j += 1
            if j >= n:
                raise GraphQLError("unterminated string")
            tokens.append(("STRING", "".join(buf)))
            i = j + 1
            continue
        if ch in _PUNCT:
            if source.startswith("...", i):
                tokens.append(("SPREAD", "..."))
                i += 3
                continue
            tokens.append(("PUNCT", ch))
            i += 1
            continue
        if source.startswith("...", i):
            tokens.append(("SPREAD", "..."))
            i += 3
            continue
        number = _NUMBER_RE.match(source, i)
        if number and (ch.isdigit() or (ch == "-" and i + 1 < n and source[i + 1].isdigit())):
            tokens.append(("NUMBER", number.group(0)))
            i = number.end()
            continue
        name = _NAME_RE.match(source, i)
        if name:
            tokens.append(("NAME", name.group(0)))
            i = name.end()
            continue
        raise GraphQLError(f"unexpected character {ch!r} at position {i}")
    tokens.append(("EOF", ""))
    return tokens


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos]

    def next(self):
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def expect(self, kind, value=None):
        token = self.next()
        if token[0] != kind or (value is not None and token[1] != value):
            raise GraphQLError(f"expected {value or kind}, found {token[1]!r}")
        return token

    def at(self, kind, value=None):
        token = self.peek()
        return token[0] == kind and (value is None or token[1] == value)

    def parse_document(self):
        operations = []
        while not self.at("EOF"):
            operations.append(self.parse_operation())
        if not operations:
            raise GraphQLError("empty document")
        return operations

    def parse_operation(self):
        operation, name = "query", None
        if self.at("NAME", "query") or self.at("NAME", "mutation") or \
                self.at("NAME", "subscription"):
            operation = self.next()[1]
            if self.at("NAME"):
                name = self.next()[1]
            if self.at("PUNCT", "("):
                self.skip_variable_definitions()
        elif self.at("NAME"):
            raise GraphQLError(f"unexpected token {self.peek()[1]!r}")
        selections = self.parse_selection_set()
        return {"operation": operation, "name": name, "selections": selections}

    def skip_variable_definitions(self):
        self.expect("PUNCT", "(")
        depth = 1
        while depth:
            token = self.next()
            if token[0] == "EOF":
                raise GraphQLError("unterminated variable definitions")
            if token == ("PUNCT", "("):
                depth += 1
            elif token == ("PUNCT", ")"):
                depth -= 1

    def parse_selection_set(self):
        self.expect("PUNCT", "{")
        selections = []
        while not self.at("PUNCT", "}"):
            if self.at("SPREAD"):
                raise GraphQLError("fragments are not supported by this mock")
            selections.append(self.parse_field())
        self.expect("PUNCT", "}")
        return selections

    def parse_field(self):
        name = self.expect("NAME")[1]
        alias = None
        if self.at("PUNCT", ":"):
            self.next()
            alias, name = name, self.expect("NAME")[1]
        arguments = self.parse_arguments() if self.at("PUNCT", "(") else {}
        children = self.parse_selection_set() if self.at("PUNCT", "{") else []
        return {"name": name, "alias": alias or name, "args": arguments,
                "selections": children}

    def parse_arguments(self):
        self.expect("PUNCT", "(")
        arguments = {}
        while not self.at("PUNCT", ")"):
            key = self.expect("NAME")[1]
            self.expect("PUNCT", ":")
            arguments[key] = self.parse_value()
        self.expect("PUNCT", ")")
        return arguments

    def parse_value(self):
        kind, value = self.peek()
        if kind == "PUNCT" and value == "$":
            self.next()
            return {"__var__": self.expect("NAME")[1]}
        if kind == "PUNCT" and value == "{":
            self.next()
            obj = {}
            while not self.at("PUNCT", "}"):
                key = self.expect("NAME")[1]
                self.expect("PUNCT", ":")
                obj[key] = self.parse_value()
            self.expect("PUNCT", "}")
            return obj
        if kind == "PUNCT" and value == "[":
            self.next()
            items = []
            while not self.at("PUNCT", "]"):
                items.append(self.parse_value())
            self.expect("PUNCT", "]")
            return items
        if kind == "STRING":
            self.next()
            return value
        if kind == "NUMBER":
            self.next()
            return float(value) if ("." in value or "e" in value.lower()) else int(value)
        if kind == "NAME":
            self.next()
            if value == "true":
                return True
            if value == "false":
                return False
            if value == "null":
                return None
            return {"__enum__": value}
        raise GraphQLError(f"unexpected value token {value!r}")


def parse(source):
    return _Parser(_tokenize(source)).parse_document()


def resolve_variables(node, variables):
    """Replace `$name` placeholders and enum wrappers with concrete values."""
    if isinstance(node, dict):
        if "__var__" in node:
            name = node["__var__"]
            if name not in (variables or {}):
                raise GraphQLError(f'variable "{name}" is used but not defined')
            return (variables or {})[name]
        if "__enum__" in node:
            return node["__enum__"]
        return {k: resolve_variables(v, variables) for k, v in node.items()}
    if isinstance(node, list):
        return [resolve_variables(item, variables) for item in node]
    return node


# ---------------------------------------------------------------------------
# Boolean expressions
# ---------------------------------------------------------------------------

_COMPARISONS = {"_eq", "_neq", "_gt", "_gte", "_lt", "_lte", "_in", "_nin",
                "_is_null", "_like", "_ilike", "_nlike", "_nilike", "_regex"}


class Schema:
    """Describes the tables, primary keys and relationships the engine serves.

    ``tables`` maps a table name to a zero-argument callable returning its rows.
    ``relationships`` maps ``(table, field)`` to
    ``(target table, local column, remote column, "object" | "array")``.
    """

    def __init__(self, tables, primary_keys, relationships, session=None):
        self.tables = tables
        self.primary_keys = primary_keys
        self.relationships = relationships
        self.session = session or {}

    def rows(self, table):
        loader = self.tables.get(table)
        return loader() if loader else []


def evaluate_where(row, expression, table, schema):
    if not expression:
        return True
    for key, value in expression.items():
        if key == "_and":
            if not all(evaluate_where(row, sub, table, schema) for sub in value or []):
                return False
        elif key == "_or":
            if not any(evaluate_where(row, sub, table, schema) for sub in value or []):
                return False
        elif key == "_not":
            if evaluate_where(row, value, table, schema):
                return False
        elif key in _COMPARISONS:
            return False
        else:
            if not _match_field(row, key, value, table, schema):
                return False
    return True


def _match_field(row, field, condition, table, schema):
    relationship = schema.relationships.get((table, field))
    if relationship:
        target, local, remote, kind = relationship
        related = _related_rows(row, relationship, schema)
        if kind == "object":
            return bool(related) and evaluate_where(related[0], condition, target, schema)
        return any(evaluate_where(item, condition, target, schema) for item in related)
    if not isinstance(condition, dict):
        return _compare(row.get(field), "_eq", condition, schema)
    return all(_compare(row.get(field), op, operand, schema)
               for op, operand in condition.items())


def _related_rows(row, relationship, schema):
    target, local, remote, _kind = relationship
    key = row.get(local)
    if key is None:
        return []
    return [r for r in schema.rows(target) if r.get(remote) == key]


def _session_value(operand, schema):
    """Hasura substitutes `X-Hasura-*` session variables inside permission filters."""
    if isinstance(operand, str) and operand.lower().startswith("x-hasura-"):
        return schema.session.get(operand.lower())
    return operand


def _compare(value, op, operand, schema):
    operand = _session_value(operand, schema)
    if op == "_is_null":
        return (value is None or value == "") is bool(operand)
    if op == "_in":
        return any(_eq(value, item) for item in operand or [])
    if op == "_nin":
        return not any(_eq(value, item) for item in operand or [])
    if op in ("_like", "_nlike", "_ilike", "_nilike"):
        hit = _like(value, operand, case_sensitive=op in ("_like", "_nlike"))
        return hit if op in ("_like", "_ilike") else not hit
    if op == "_regex":
        return bool(re.search(str(operand), str(value or "")))
    if op == "_eq":
        return _eq(value, operand)
    if op == "_neq":
        return not _eq(value, operand)
    if op in ("_gt", "_gte", "_lt", "_lte"):
        return _order(value, operand, op)
    raise GraphQLError(f"unknown operator {op}")


def _eq(value, operand):
    if isinstance(value, bool) or isinstance(operand, bool):
        return bool(value) == bool(operand)
    if isinstance(value, int) and isinstance(operand, str):
        try:
            operand = int(operand)
        except ValueError:
            return False
    if isinstance(value, str) and isinstance(operand, (int, float)):
        operand = str(operand)
    return value == operand


def _like(value, pattern, case_sensitive):
    regex = "^" + re.escape(str(pattern)).replace("%", ".*").replace("_", ".") + "$"
    return bool(re.match(regex, str(value or ""), 0 if case_sensitive else re.IGNORECASE))


def _order(value, operand, op):
    if value is None or operand is None:
        return False
    if isinstance(value, (int, float)) and isinstance(operand, str):
        try:
            operand = type(value)(operand)
        except ValueError:
            return False
    if isinstance(value, str) and isinstance(operand, (int, float)):
        operand = str(operand)
    try:
        return {"_gt": value > operand, "_gte": value >= operand,
                "_lt": value < operand, "_lte": value <= operand}[op]
    except TypeError:
        return False


def apply_order_by(rows, order_by, table, schema):
    if not order_by:
        return rows
    clauses = order_by if isinstance(order_by, list) else [order_by]
    out = list(rows)
    for clause in reversed(clauses):
        for field, direction in (clause or {}).items():
            descending = str(direction).startswith("desc")
            out.sort(key=lambda r: (r.get(field) is None, _sort_key(r.get(field))),
                     reverse=descending)
    return out


def _sort_key(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    return str(value)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

class Executor:
    """Runs a parsed operation against a :class:`Schema`.

    ``permission_for(table, action)`` supplies the row filter, column allow-list
    and row limit for the caller's role, mirroring Hasura's permission layer.
    A table with no permission is absent from the role's schema, which is why an
    unpermitted root field reports "not found in type: 'query_root'".
    """

    def __init__(self, schema, permission_for=None, mutations=None):
        self.schema = schema
        self.permission_for = permission_for or (lambda table, action: {})
        self.mutations = mutations or {}

    def execute(self, operation, variables=None):
        data = {}
        for field in operation["selections"]:
            args = resolve_variables(field["args"], variables)
            data[field["alias"]] = self._root(operation["operation"], field, args,
                                              variables)
        return data

    def _root(self, operation, field, args, variables):
        name = field["name"]
        if operation == "mutation":
            return self._mutation(name, field, args, variables)
        if name.endswith("_aggregate"):
            table = name[: -len("_aggregate")]
            return self._aggregate(table, field, args, variables)
        if name.endswith("_by_pk"):
            table = name[: -len("_by_pk")]
            return self._by_pk(table, field, args, variables)
        return self._select(name, field, args, variables)

    def _permitted(self, table, action="select"):
        if table not in self.schema.tables:
            raise GraphQLError(
                f"field '{table}' not found in type: 'query_root'", "validation-failed")
        permission = self.permission_for(table, action)
        if permission is None:
            raise GraphQLError(
                f"field '{table}' not found in type: 'query_root'", "validation-failed")
        return permission

    def _visible(self, table, action="select"):
        permission = self._permitted(table, action)
        rows = self.schema.rows(table)
        row_filter = permission.get("filter") if permission else None
        if row_filter:
            rows = [r for r in rows if evaluate_where(r, row_filter, table, self.schema)]
        return rows, permission

    def _select(self, table, field, args, variables):
        rows, permission = self._visible(table)
        rows = self._filter_sort_page(rows, table, args, permission)
        return [self._project(table, r, field["selections"], permission, variables)
                for r in rows]

    def _by_pk(self, table, field, args, variables):
        rows, permission = self._visible(table)
        key = self.schema.primary_keys.get(table, "id")
        wanted = args.get(key)
        match = next((r for r in rows if _eq(r.get(key), wanted)), None)
        return self._project(table, match, field["selections"], permission, variables) \
            if match else None

    def _aggregate(self, table, field, args, variables):
        rows, permission = self._visible(table)
        rows = self._filter_sort_page(rows, table, args, permission)
        out = {}
        for child in field["selections"]:
            if child["name"] == "aggregate":
                out[child["alias"]] = self._aggregate_block(rows, child)
            elif child["name"] == "nodes":
                out[child["alias"]] = [
                    self._project(table, r, child["selections"], permission, variables)
                    for r in rows]
        return out

    def _aggregate_block(self, rows, node):
        block = {}
        for child in node["selections"]:
            if child["name"] == "count":
                block[child["alias"]] = len(rows)
                continue
            values_by_field = {}
            for leaf in child["selections"]:
                values = [r.get(leaf["name"]) for r in rows
                          if isinstance(r.get(leaf["name"]), (int, float))
                          and not isinstance(r.get(leaf["name"]), bool)]
                values_by_field[leaf["alias"]] = self._reduce(child["name"], values)
            block[child["alias"]] = values_by_field
        return block

    @staticmethod
    def _reduce(function, values):
        if not values:
            return None
        if function == "sum":
            return sum(values)
        if function == "avg":
            return round(sum(values) / len(values), 4)
        if function == "min":
            return min(values)
        if function == "max":
            return max(values)
        return None

    def _filter_sort_page(self, rows, table, args, permission):
        where = args.get("where")
        if where:
            rows = [r for r in rows if evaluate_where(r, where, table, self.schema)]
        distinct_on = args.get("distinct_on")
        if distinct_on:
            seen, unique = set(), []
            for row in rows:
                key = row.get(distinct_on)
                if key not in seen:
                    seen.add(key)
                    unique.append(row)
            rows = unique
        rows = apply_order_by(rows, args.get("order_by"), table, self.schema)
        offset = int(args.get("offset") or 0)
        ceiling = (permission or {}).get("limit")
        limit = args.get("limit")
        limit = int(limit) if limit is not None else ceiling
        if ceiling is not None and limit is not None:
            limit = min(int(limit), int(ceiling))
        rows = rows[offset:]
        return rows[:int(limit)] if limit is not None else rows

    def _project(self, table, row, selections, permission, variables):
        if row is None:
            return None
        allowed = (permission or {}).get("columns")
        out = {}
        for field in selections or []:
            name = field["name"]
            relationship = self.schema.relationships.get((table, name))
            if relationship:
                out[field["alias"]] = self._project_relationship(
                    row, relationship, field, variables)
                continue
            if name == "__typename":
                out[field["alias"]] = table
                continue
            if allowed and name not in allowed:
                raise GraphQLError(
                    f"field '{name}' not found in type: '{table}'", "validation-failed")
            out[field["alias"]] = row.get(name)
        return out

    def _project_relationship(self, row, relationship, field, variables):
        target, _local, _remote, kind = relationship
        permission = self.permission_for(target, "select")
        if permission is None:
            raise GraphQLError(
                f"field '{field['name']}' not found in type: 'query_root'",
                "validation-failed")
        related = _related_rows(row, relationship, self.schema)
        row_filter = (permission or {}).get("filter")
        if row_filter:
            related = [r for r in related
                       if evaluate_where(r, row_filter, target, self.schema)]
        args = resolve_variables(field["args"], variables)
        if kind == "object":
            match = related[0] if related else None
            return self._project(target, match, field["selections"], permission, variables)
        related = self._filter_sort_page(related, target, args, permission)
        return [self._project(target, r, field["selections"], permission, variables)
                for r in related]

    def _mutation(self, name, field, args, variables):
        handler = self.mutations.get(name)
        if not handler:
            raise GraphQLError(
                f"field '{name}' not found in type: 'mutation_root'", "validation-failed")
        table, row = handler(args)
        permission = self.permission_for(table, "select") or {}
        if name.startswith("delete_"):
            return self._project(table, row, field["selections"], permission, variables)
        return self._project(table, row, field["selections"], permission, variables)
