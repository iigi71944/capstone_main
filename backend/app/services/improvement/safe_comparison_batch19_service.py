"""Batch 19: conservative operator comparison call -> syntax transformer.

Only module-level simple assignments of `operator.eq/ne/lt/le/gt/ge` with
literal primitive operands are rewritten. A sole prior `import operator` is
required, and source-level rebindings/writes to `operator` are rejected.

The transformation is source-span based and does not execute submitted code.
It is not a proof of equivalence for arbitrary Python sources: runtime
monkeypatching, execution hooks, or dynamic imports cannot be ruled out.
"""
from __future__ import annotations

import ast

_COMPARISONS = {
    'eq': '==', 'ne': '!=', 'lt': '<', 'le': '<=', 'gt': '>', 'ge': '>=',
}
_ALLOWED_LITERAL_TYPES = (int, float, bool, str)


def _primitive(node: ast.AST) -> bool:
    return (isinstance(node, ast.Constant)
            and type(node.value) in _ALLOWED_LITERAL_TYPES)


def _operator_binding_safe(tree: ast.Module, statement: ast.Assign) -> bool:
    imports = [item for item in tree.body
               if isinstance(item, ast.Import)
               and any(alias.name == 'operator' and alias.asname is None
                       for alias in item.names)]
    if len(imports) != 1 or imports[0].lineno >= statement.lineno:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == 'operator' and isinstance(node.ctx, (ast.Store, ast.Del)):
            return False
        if isinstance(node, ast.arg) and node.arg == 'operator':
            return False
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == 'operator':
            return False
        if isinstance(node, (ast.Global, ast.Nonlocal)) and 'operator' in node.names:
            return False
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'operator' and not isinstance(node.ctx, ast.Load):
            return False
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound = alias.asname or alias.name.split('.')[0]
                if bound == 'operator' and not (isinstance(node, ast.Import) and alias.name == 'operator' and alias.asname is None):
                    return False
    return True


def transform_operator_comparison_to_syntax(code: str) -> str:
    """Rewrite only demonstrably local literal comparison calls.

    Whole-file AST is checked before any edit. Individual calls and original
    literal lexemes are retained as byte slices to preserve other formatting.
    """
    if not isinstance(code, str) or not code or len(code) > 250_000:
        return code
    try:
        tree = ast.parse(code)
        raw = code.encode('utf-8')
        offsets = [0]
        for line in code.splitlines(keepends=True):
            offsets.append(offsets[-1] + len(line.encode('utf-8')))
        edits = []
        for statement in tree.body:
            if not (isinstance(statement, ast.Assign)
                    and len(statement.targets) == 1
                    and isinstance(statement.targets[0], ast.Name)):
                continue
            call = statement.value
            if not (isinstance(call, ast.Call)
                    and not call.keywords and len(call.args) == 2
                    and all(_primitive(arg) for arg in call.args)
                    and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == 'operator'
                    and call.func.attr in _COMPARISONS
                    and _operator_binding_safe(tree, statement)):
                continue
            def span(node: ast.AST) -> tuple[int, int]:
                return (offsets[node.lineno - 1] + node.col_offset,
                        offsets[node.end_lineno - 1] + node.end_col_offset)
            start, end = span(call)
            if b'#' in raw[start:end] or b'\n' in raw[start:end] or b'\r' in raw[start:end]:
                continue  # preserve comments and multi-line layout
            a, b = (raw[lo:hi] for lo, hi in (span(call.args[0]), span(call.args[1])))
            replacement = b'(' + a + b' ' + _COMPARISONS[call.func.attr].encode('ascii') + b' ' + b + b')'
            edits.append((start, end, replacement))
        if not edits:
            return code
        for start, end, replacement in sorted(edits, reverse=True):
            raw = raw[:start] + replacement + raw[end:]
        after = raw.decode('utf-8')
        ast.parse(after)
        return after
    except (SyntaxError, ValueError, IndexError, AttributeError, UnicodeError, RecursionError, MemoryError):
        return code
