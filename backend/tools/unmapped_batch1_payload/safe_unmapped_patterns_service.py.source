"""First conservative transform batch for previously compare-only concept tags.

The public actions remain opt-in through the *existing saved concept tags*.
No changes to how a style is stored.  Rewrites are intentionally narrow and
leave unrelated source bytes untouched; unsupported code is a no-op.

Supported families:
- Nested conditions: pure `if a and b [and c...]` with no else.
- Literal collections: calls to *unshadowed* empty list/dict/tuple builtins.
- Multiple returns: final-result local variable patterns with pure values.

Not a proof of semantic equivalence for Python tracing, dynamic namespace
manipulation, monkeypatching or every possible object. The existing application's
execution comparison remains mandatory to assess a rewritten program.
"""
from __future__ import annotations

import ast
import copy
import io
import re
import tokenize

_MAX_EDITS = 80
_DYNAMIC = frozenset({
    'locals', 'globals', 'vars', 'eval', 'exec', '__import__',
    'compile', 'inspect', 'sys', 'builtins', 'setattr', 'delattr',
})


def _tree(source: str) -> ast.Module | None:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, TypeError):
        return None
    return tree


def _comments(source: str) -> set[int] | None:
    try:
        return {
            t.start[0]
            for t in tokenize.generate_tokens(io.StringIO(source).readline)
            if t.type == tokenize.COMMENT
        }
    except (tokenize.TokenError, IndentationError):
        return None


def _unsafe_dynamic(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _DYNAMIC:
            return True
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if (alias.name.split('.')[0] in _DYNAMIC
                        or (alias.asname or '') in _DYNAMIC):
                    return True
    return False


def _simple_condition(expr: ast.AST) -> bool:
    """Permit only deterministic names/literals, comparisons, and boolean ops.

    No calls, attributes, subscriptions, assignment expressions, awaits etc.
    This deliberately rejects custom truthy objects only at runtime; callers
    still run the existing observed-behavior comparison.
    """
    if isinstance(expr, ast.Name):
        return isinstance(expr.ctx, ast.Load)
    if isinstance(expr, ast.Constant):
        return type(expr.value) in (bool, int, float, str, type(None))
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
        return _simple_condition(expr.operand)
    if isinstance(expr, ast.BoolOp) and isinstance(expr.op, (ast.And, ast.Or)):
        return all(_simple_condition(value) for value in expr.values)
    if isinstance(expr, ast.Compare):
        allowed = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
                   ast.Is, ast.IsNot, ast.In, ast.NotIn)
        return all(isinstance(op, allowed) for op in expr.ops) and all(
            _simple_condition(item) for item in [expr.left, *expr.comparators]
        )
    return False


def _first_editable_nested_if(source: str, min_terms: int = 2) -> tuple[int, int, str] | None:
    """Return physical line replacement (start, end_exclusive, text)."""
    tree = _tree(source)
    comments = _comments(source)
    if tree is None or comments is None or _unsafe_dynamic(tree):
        return None
    lines = source.splitlines(keepends=True)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.If) and not node.orelse
                and isinstance(node.test, ast.BoolOp)
                and isinstance(node.test.op, ast.And)
                and min_terms <= len(node.test.values) <= 4
                and node.body and node.end_lineno):
            continue
        if any(not _simple_condition(part) for part in node.test.values):
            continue
        if (node.lineno != node.test.lineno or
                node.test.end_lineno != node.lineno or
                node.body[0].lineno <= node.lineno):
            continue
        start, end = node.lineno, node.end_lineno
        if any(start <= row <= end for row in comments):
            continue
        line = lines[start - 1]
        stripped = line.rstrip('\r\n')
        match = re.match(r'(?P<indent>[ \t]*)if[ \t]+.*:[ \t]*$', stripped)
        if not match:
            continue
        indent = match.group('indent')
        body_first = lines[node.body[0].lineno - 1]
        body_indent = body_first[:len(body_first) - len(body_first.lstrip(' \t'))]
        if not body_indent.startswith(indent) or len(body_indent) <= len(indent):
            continue
        unit = body_indent[len(indent):]
        if not unit or ('\t' in unit and ' ' in unit):
            continue
        eol = '\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else '\r' if line.endswith('\r') else ''
        if not eol:
            continue
        tests = [ast.get_source_segment(source, part) for part in node.test.values]
        if any(not part or '\n' in part or '\r' in part for part in tests):
            continue
        # `if (a and b):` is fine; original block is retained without AST-unparse.
        headers = ''.join((indent + unit * index + 'if ' + part.strip() + ':' + eol)
                          for index, part in enumerate(tests))
        # Remove one indentation level from the first header (the original if
        # had already occupied it).  Each original body line gains k-1 levels.
        moved = []
        for original_line in lines[start-1:end]:
            # Reject weird mixed indentation inside the body rather than breaking it.
            if original_line.strip():
                if not original_line.startswith(indent):
                    moved = []
                    break
                moved.append(unit * (len(tests)-1) + original_line)
            else:
                moved.append(original_line)
        if not moved:
            continue
        # `moved` contains the original header; drop it and indent only body.
        replacement = headers + ''.join(moved[1:])
        trial = ''.join(lines[:start-1]) + replacement + ''.join(lines[end:])
        if _tree(trial) is None:
            continue
        return start-1, end, replacement
    return None


def _nested_transform(source: str, min_terms: int) -> str:
    if not isinstance(source, str):
        return source
    for _ in range(_MAX_EDITS):
        item = _first_editable_nested_if(source, min_terms)
        if item is None:
            return source
        start, end, replacement = item
        lines = source.splitlines(keepends=True)
        trial = ''.join(lines[:start]) + replacement + ''.join(lines[end:])
        if trial == source:
            return source
        source = trial
    return source


def transform_to_nested_conditions(source: str) -> str:
    return _nested_transform(source, 2)


def transform_to_deep_conditions(source: str) -> str:
    """Only three-/four-way AND introduces at least three if-levels."""
    return _nested_transform(source, 3)


def _builtin_shadowed(tree: ast.AST, names: set[str]) -> set[str]:
    shadowed = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            shadowed.add(node.id)
        if isinstance(node, ast.arg):
            shadowed.add(node.arg)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            shadowed.add(node.name)
        if isinstance(node, ast.alias):
            shadowed.add(node.asname or node.name.split('.')[0])
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            shadowed.update(node.names)
        if isinstance(node, (ast.ExceptHandler,)) and node.name:
            shadowed.add(node.name)
    return shadowed & names


def transform_to_literal_collections(source: str) -> str:
    """Three patterns: list()->[], dict()->{}, tuple()->(); keep all other bytes."""
    tree = _tree(source)
    comments = _comments(source)
    if tree is None or comments is None or _unsafe_dynamic(tree):
        return source
    literals = {'list': '[]', 'dict': '{}', 'tuple': '()'}
    forbidden = _builtin_shadowed(tree, set(literals))
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line.encode('utf-8')))
    source_bytes = source.encode('utf-8')
    edits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in literals and node.func.id not in forbidden
                and not node.args and not node.keywords
                and node.end_lineno is not None and node.end_col_offset is not None
                and node.lineno == node.end_lineno):
            continue
        if node.lineno in comments:
            # Even if a comment is after the call, skip to preserve attachment.
            continue
        start = offsets[node.lineno-1] + node.col_offset
        end = offsets[node.end_lineno-1] + node.end_col_offset
        if not (0 <= start < end <= len(source_bytes)):
            continue
        fragment = source_bytes[start:end].decode('utf-8', errors='ignore')
        if not re.fullmatch(r'(?:list|dict|tuple)\s*\(\s*\)', fragment):
            continue
        edits.append((start, end, literals[node.func.id].encode('utf-8')))
    if not edits:
        return source
    output = source_bytes
    for start, end, replacement in sorted(edits[:_MAX_EDITS], reverse=True):
        output = output[:start] + replacement + output[end:]
    try:
        changed = output.decode('utf-8')
    except UnicodeDecodeError:
        return source
    return changed if _tree(changed) is not None else source


def _simple_return_value(expr: ast.expr) -> bool:
    if isinstance(expr, ast.Constant):
        return type(expr.value) in (bool, int, float, str, type(None))
    if isinstance(expr, ast.Name):
        return isinstance(expr.ctx, ast.Load)
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, (ast.USub, ast.UAdd)):
        return isinstance(expr.operand, ast.Constant) and type(expr.operand.value) in (int, float)
    return False


def _assignment_to(stmt: ast.stmt, name: str | None = None) -> tuple[str, ast.expr] | None:
    if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
        return None
    target = stmt.targets[0].id
    if name is not None and target != name:
        return None
    if not _simple_return_value(stmt.value):
        return None
    return target, stmt.value


def _reads_name(expr: ast.AST, name: str) -> bool:
    return any(isinstance(n, ast.Name) and n.id == name for n in ast.walk(expr))


def _return_pair(stmt: ast.stmt, ret: ast.stmt) -> list[ast.stmt] | None:
    if not (isinstance(ret, ast.Return) and isinstance(ret.value, ast.Name)):
        return None
    name = ret.value.id
    # Case C: result = A if predicate else B ; return result
    if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == name and isinstance(stmt.value, ast.IfExp)):
        expr = stmt.value
        if (_simple_condition(expr.test) and _simple_return_value(expr.body)
                and _simple_return_value(expr.orelse)
                and not _reads_name(expr, name)):
            return [ast.If(test=copy.deepcopy(expr.test),
                           body=[ast.Return(value=copy.deepcopy(expr.body))],
                           orelse=[ast.Return(value=copy.deepcopy(expr.orelse))])]
    # Case B: if predicate: result = A ; else: result = B ; return result
    if (isinstance(stmt, ast.If) and _simple_condition(stmt.test)
            and len(stmt.body) == 1 and len(stmt.orelse) == 1):
        a = _assignment_to(stmt.body[0], name)
        b = _assignment_to(stmt.orelse[0], name)
        if a and b and not any(_reads_name(expr, name)
                               for expr in (stmt.test, a[1], b[1])):
            return [ast.If(test=copy.deepcopy(stmt.test),
                           body=[ast.Return(value=copy.deepcopy(a[1]))],
                           orelse=[ast.Return(value=copy.deepcopy(b[1]))])]
    return None


def _return_triple(a: ast.stmt, mid: ast.stmt, ret: ast.stmt) -> list[ast.stmt] | None:
    # Case A: result = constant; if predicate: result = constant; return result
    if not (isinstance(ret, ast.Return) and isinstance(ret.value, ast.Name)):
        return None
    name = ret.value.id
    initial = _assignment_to(a, name)
    if not (initial and isinstance(initial[1], ast.Constant)
            and isinstance(mid, ast.If) and not mid.orelse
            and len(mid.body) == 1 and _simple_condition(mid.test)):
        return None
    branch = _assignment_to(mid.body[0], name)
    if branch and not _reads_name(mid.test, name) and not _reads_name(branch[1], name):
        return [ast.If(test=copy.deepcopy(mid.test),
                       body=[ast.Return(value=copy.deepcopy(branch[1]))],
                       orelse=[]),
                ast.Return(value=copy.deepcopy(initial[1]))]
    return None


def _first_editable_multiple_return(source: str) -> tuple[int, int, str] | None:
    tree = _tree(source)
    comments = _comments(source)
    if tree is None or comments is None or _unsafe_dynamic(tree):
        return None
    lines = source.splitlines(keepends=True)
    for func in ast.walk(tree):
        if not isinstance(func, ast.FunctionDef):
            continue
        if func.decorator_list or any(isinstance(x, (ast.Yield, ast.YieldFrom, ast.Await,
                                                   ast.Global, ast.Nonlocal, ast.Lambda,
                                                   ast.FunctionDef, ast.ClassDef))
                                      for x in ast.walk(func) if x is not func):
            continue
        # Apply only to trailing function-body statements. Never change a
        # variable that might be observed by later statements.
        body = func.body
        options: list[tuple[list[ast.stmt], list[ast.stmt]]] = []
        if len(body) >= 2:
            changed = _return_pair(body[-2], body[-1])
            if changed:
                options.append((body[-2:], changed))
        if len(body) >= 3:
            changed = _return_triple(body[-3], body[-2], body[-1])
            if changed:
                options.append((body[-3:], changed))
        for originals, replacements in options:
            start, end = originals[0].lineno, originals[-1].end_lineno
            if end is None or start < 1 or end > len(lines):
                continue
            if any(start <= row <= end for row in comments):
                continue
            prefix = lines[start - 1][:len(lines[start - 1]) - len(lines[start - 1].lstrip(' \t'))]
            if not prefix or not all(
                    lines[row - 1][:len(lines[row - 1]) - len(lines[row - 1].lstrip(' \t'))] == prefix
                    for row in (item.lineno for item in originals)):
                continue
            # Ensure that the replacement edits whole physical lines only.
            if not all(lines[item.lineno-1][len(prefix):].strip() for item in originals):
                continue
            try:
                replacement_ast = ast.fix_missing_locations(ast.Module(
                    body=copy.deepcopy(replacements), type_ignores=[]))
                unparsed = ast.unparse(replacement_ast)
            except (ValueError, TypeError):
                continue
            newline = '\r\n' if lines[start-1].endswith('\r\n') else '\n'
            snippet = newline.join(prefix + row for row in unparsed.splitlines())
            if lines[end - 1].endswith(('\n', '\r')):
                snippet += newline
            trial = ''.join(lines[:start-1]) + snippet + ''.join(lines[end:])
            if _tree(trial) is not None:
                return start-1, end, snippet
    return None


def transform_to_multiple_returns(source: str) -> str:
    if not isinstance(source, str):
        return source
    for _ in range(_MAX_EDITS):
        change = _first_editable_multiple_return(source)
        if change is None:
            return source
        start, end, snippet = change
        lines = source.splitlines(keepends=True)
        trial = ''.join(lines[:start]) + snippet + ''.join(lines[end:])
        if trial == source:
            return source
        source = trial
    return source
