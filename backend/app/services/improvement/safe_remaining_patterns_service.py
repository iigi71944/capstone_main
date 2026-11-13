"""Conservative syntax transforms for saved-style preference (batch 3).

Only narrow, structurally equivalent forms are supported:
- method decorator @staticmethod/@classmethod/@property <-> method = decorator(method)
- next(iterator, literal_default) <-> try/except StopIteration with literal fallback
- a <op> b <-> operator.<op>(a, b), when `import operator` is prior and stable

No user code is executed here. Candidate statements containing comments or
introspection are skipped. Full semantic equivalence for arbitrary dynamic
Python programs is not claimed; application-level validation remains required.
"""
from __future__ import annotations

import ast
import copy
import io
import tokenize
from dataclasses import dataclass

from app.services.improvement.safe_dict_comprehension_service import (
    _comments, _prepare_edit, _statement_blocks,
)
from app.services.improvement.safe_structural_patterns_service import (
    _is_shadowed, _sensitive,
)

_DECORATORS = frozenset({'staticmethod', 'classmethod', 'property'})
_BINOP_METHODS = {
    ast.Add: 'add', ast.Sub: 'sub', ast.Mult: 'mul',
    ast.Div: 'truediv', ast.FloorDiv: 'floordiv', ast.Mod: 'mod',
}
_INVERSE_BINOPS = {value: key for key, value in _BINOP_METHODS.items()}


@dataclass(frozen=True)
class _Edit:
    start: int
    end: int
    replacement: bytes


def _safe_to_read(code: str):
    try:
        parsed = ast.parse(code)
        if _sensitive(parsed):
            return None
        return parsed, _comments(code)
    except (SyntaxError, UnicodeError, TypeError, tokenize.TokenError):
        return None


def _render(source: str, first: ast.stmt, last: ast.stmt,
            replacements: list[ast.stmt], comments: set[int]):
    return _prepare_edit(source, first, last, replacements, comments)


def _rewrite_edits(code: str, edits: list[_Edit]) -> str:
    if not edits:
        return code
    output = code.encode('utf-8')
    # Reject overlapping rewrites: first accepted edit wins.
    remaining = []
    for item in sorted(edits, key=lambda e: e.start):
        if remaining and item.start < remaining[-1].end:
            continue
        remaining.append(item)
    for item in reversed(remaining):
        output = output[:item.start] + item.replacement + output[item.end:]
    try:
        result = output.decode('utf-8')
        ast.parse(result)
        return result
    except (UnicodeError, SyntaxError):
        return code


def _is_simple_method(method: ast.AST) -> bool:
    return isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and not (
        getattr(method, 'type_params', ()) or getattr(method, 'type_comment', None)
    )


def _decorator_to_assignment(code: str, method: ast.stmt, comments: set[int]) -> _Edit | None:
    """Rewrite the method including its initial @ line; leave class intact."""
    if not _is_simple_method(method):
        return None
    if len(method.decorator_list) != 1:
        return None
    deco = method.decorator_list[0]
    if not isinstance(deco, ast.Name) or deco.id not in _DECORATORS:
        return None
    if method.end_lineno is None or method.end_col_offset is None:
        return None
    start_line = deco.lineno
    if any(start_line <= n <= method.end_lineno for n in comments):
        return None
    lines = code.splitlines(keepends=True)
    if start_line > len(lines) or method.end_lineno > len(lines):
        return None
    # On decorated functions, the decorator expression col_offset points
    # immediately *after* @. Determine indent by the @ token position.
    deco_line = lines[start_line - 1]
    marker = deco_line.find('@')
    if marker < 0 or deco_line[:marker].strip():
        return None
    prefix = deco_line[:marker]
    if '\t' in prefix:
        return None
    end_bytes = lines[method.end_lineno - 1].encode('utf-8')
    if end_bytes[method.end_col_offset:].strip():
        return None
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line.encode('utf-8')))
    m = copy.deepcopy(method)
    m.decorator_list = []
    assignment = ast.Assign(
        targets=[ast.Name(id=m.name, ctx=ast.Store())],
        value=ast.Call(func=ast.Name(id=deco.id, ctx=ast.Load()),
                       args=[ast.Name(id=m.name, ctx=ast.Load())], keywords=[]),
    )
    body = ast.Module(body=[m, assignment], type_ignores=[])
    text = ast.unparse(ast.fix_missing_locations(body))
    nl = '\r\n' if '\r\n' in code else '\n'
    output = (nl + prefix).join(text.splitlines()).encode('utf-8')
    return _Edit(offsets[start_line - 1] + len(prefix.encode('utf-8')),
                 offsets[method.end_lineno - 1] + method.end_col_offset,
                 output)


def _assignment_to_decorator(code: str, first: ast.stmt, second: ast.stmt,
                             comments: set[int]) -> _Edit | None:
    if not _is_simple_method(first) or first.decorator_list:
        return None
    if not (isinstance(second, ast.Assign) and len(second.targets) == 1
            and isinstance(second.targets[0], ast.Name)
            and second.targets[0].id == first.name
            and isinstance(second.value, ast.Call)
            and not second.value.keywords and len(second.value.args) == 1
            and isinstance(second.value.func, ast.Name)
            and second.value.func.id in _DECORATORS
            and isinstance(second.value.args[0], ast.Name)
            and second.value.args[0].id == first.name):
        return None
    m = copy.deepcopy(first)
    m.decorator_list = [ast.Name(id=second.value.func.id, ctx=ast.Load())]
    edit = _render(code, first, second, [m], comments)
    if edit is None:
        return None
    return _Edit(edit.start, edit.end, edit.replacement)


def _rewrite_decorators(code: str, to_decorator: bool) -> str:
    parsed = _safe_to_read(code)
    if parsed is None:
        return code
    tree, comments = parsed
    edits: list[_Edit] = []
    for klass in ast.walk(tree):
        if not isinstance(klass, ast.ClassDef):
            continue
        # Only direct class methods, not methods nested in other statements.
        body = klass.body
        for i, statement in enumerate(body):
            if to_decorator and i + 1 < len(body):
                result = _assignment_to_decorator(code, statement, body[i + 1], comments)
            elif not to_decorator:
                result = _decorator_to_assignment(code, statement, comments)
            else:
                result = None
            if result is not None:
                edits.append(result)
    return _rewrite_edits(code, edits)


def transform_assignment_to_decorator(code: str) -> str:
    """Class method followed by `name = staticmethod(name)` -> @staticmethod."""
    return _rewrite_decorators(code, to_decorator=True)


def transform_decorator_to_assignment(code: str) -> str:
    return _rewrite_decorators(code, to_decorator=False)


def _is_literal_default(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and type(node.value) in (int, str, bool, type(None), float)


def _next_call(call: ast.AST, num_args: int) -> bool:
    return (isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name) and call.func.id == 'next'
            and not call.keywords and len(call.args) == num_args
            and isinstance(call.args[0], ast.Name)
            and (num_args == 1 or _is_literal_default(call.args[1])))


def _make_next_try(stmt: ast.Assign) -> ast.Try | None:
    if not (len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name)
            and _next_call(stmt.value, 2)):
        return None
    assert isinstance(stmt.value, ast.Call)
    simple = copy.deepcopy(stmt)
    simple.value.args = [copy.deepcopy(stmt.value.args[0])]
    fallback = ast.Assign(targets=[copy.deepcopy(stmt.targets[0])],
                          value=copy.deepcopy(stmt.value.args[1]))
    return ast.Try(body=[simple],
                   handlers=[ast.ExceptHandler(type=ast.Name('StopIteration', ast.Load()),
                                               name=None, body=[fallback])],
                   orelse=[], finalbody=[])


def _make_next_default(stmt: ast.Try) -> ast.Assign | None:
    if (len(stmt.body) != 1 or len(stmt.handlers) != 1
            or stmt.orelse or stmt.finalbody):
        return None
    handler = stmt.handlers[0]
    first = stmt.body[0]
    if not (isinstance(first, ast.Assign) and len(first.targets) == 1
            and isinstance(first.targets[0], ast.Name)
            and _next_call(first.value, 1)
            and handler.name is None and isinstance(handler.type, ast.Name)
            and handler.type.id == 'StopIteration'
            and len(handler.body) == 1):
        return None
    fallback = handler.body[0]
    if not (isinstance(fallback, ast.Assign) and len(fallback.targets) == 1
            and isinstance(fallback.targets[0], ast.Name)
            and fallback.targets[0].id == first.targets[0].id
            and _is_literal_default(fallback.value)):
        return None
    result = copy.deepcopy(first)
    result.value.args.append(copy.deepcopy(fallback.value))
    return result


def _rewrite_next(code: str, to_try: bool) -> str:
    parsed = _safe_to_read(code)
    if parsed is None:
        return code
    tree, comments = parsed
    if _is_shadowed(tree, 'next') or _is_shadowed(tree, 'StopIteration'):
        return code
    edits: list[_Edit] = []
    for block in _statement_blocks(tree):
        for stmt in block:
            replacement = (_make_next_try(stmt) if isinstance(stmt, ast.Assign) else None) if to_try else (
                _make_next_default(stmt) if isinstance(stmt, ast.Try) else None)
            if replacement is not None:
                edit = _render(code, stmt, stmt, [replacement], comments)
                if edit:
                    edits.append(_Edit(edit.start, edit.end, edit.replacement))
    return _rewrite_edits(code, edits)


def transform_next_default_to_try(code: str) -> str:
    return _rewrite_next(code, to_try=True)


def transform_try_to_next_default(code: str) -> str:
    return _rewrite_next(code, to_try=False)


def _operator_import_before(tree: ast.Module, statement: ast.stmt) -> bool:
    """Require unique, direct, prior import operator; reject rebindings."""
    imports = [(i, s) for i, s in enumerate(tree.body)
               if isinstance(s, ast.Import) and any(a.name == 'operator' and a.asname is None
                                                    for a in s.names)]
    if len(imports) != 1:
        return False
    if imports[0][1].lineno >= statement.lineno:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == 'operator' and isinstance(node.ctx, (ast.Store, ast.Del)):
            return False
        if isinstance(node, ast.arg) and node.arg == 'operator':
            return False
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and node.name == 'operator':
            return False
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'operator' and not isinstance(node.ctx, ast.Load):
            return False
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bind = alias.asname or alias.name.split('.')[0]
                if bind == 'operator' and not (isinstance(node, ast.Import) and alias.name == 'operator' and alias.asname is None):
                    return False
    return True


def _operator_expression(stmt: ast.stmt, to_call: bool):
    if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name)):
        return None
    expr = stmt.value
    # Function-call argument evaluation happens after looking up operator.add,
    # whereas a binary expression evaluates operands before its operation.
    # Only pure literal/name operands can safely be reordered this way.
    def pure_operand(node):
        return all(isinstance(child, (ast.Name, ast.Constant, ast.UnaryOp,
                                      ast.UAdd, ast.USub, ast.Not, ast.Load,
                                      ast.Add, ast.Sub, ast.Mult, ast.Div,
                                      ast.FloorDiv, ast.Mod, ast.BinOp))
                   for child in ast.walk(node))
    if to_call:
        if not isinstance(expr, ast.BinOp):
            return None
        method = _BINOP_METHODS.get(type(expr.op))
        if not (pure_operand(expr.left) and pure_operand(expr.right)):
            return None
        if method is None:
            return None
        replacement = ast.Call(
            func=ast.Attribute(value=ast.Name('operator', ast.Load()), attr=method, ctx=ast.Load()),
            args=[copy.deepcopy(expr.left), copy.deepcopy(expr.right)], keywords=[])
    else:
        if not (isinstance(expr, ast.Call) and not expr.keywords
                and len(expr.args) == 2 and isinstance(expr.func, ast.Attribute)
                and isinstance(expr.func.value, ast.Name)
                and expr.func.value.id == 'operator'
                and expr.func.attr in _INVERSE_BINOPS):
            return None
        if not all(pure_operand(arg) for arg in expr.args):
            return None
        replacement = ast.BinOp(left=copy.deepcopy(expr.args[0]),
                                op=_INVERSE_BINOPS[expr.func.attr](),
                                right=copy.deepcopy(expr.args[1]))
    result = copy.deepcopy(stmt)
    result.value = replacement
    return result


def _rewrite_operator(code: str, to_call: bool) -> str:
    parsed = _safe_to_read(code)
    if parsed is None:
        return code
    tree, comments = parsed
    edits: list[_Edit] = []
    for statement in tree.body:
        if not _operator_import_before(tree, statement):
            continue
        replacement = _operator_expression(statement, to_call)
        if replacement is not None:
            edit = _render(code, statement, statement, [replacement], comments)
            if edit:
                edits.append(_Edit(edit.start, edit.end, edit.replacement))
    return _rewrite_edits(code, edits)


def transform_arithmetic_to_operator_call(code: str) -> str:
    return _rewrite_operator(code, to_call=True)


def transform_operator_call_to_arithmetic(code: str) -> str:
    return _rewrite_operator(code, to_call=False)
