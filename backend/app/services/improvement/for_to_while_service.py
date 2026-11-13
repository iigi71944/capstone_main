"""Convert synchronous for loops to semantically closer while loops.

Unlike index-based rewriting, this uses the iterable's own iterator so it
works with lists, tuples, strings, generators, ranges, and custom iterables.
It retains break/continue/for-else behavior for supported programs.

Rewrite complete source spans; leave unsupported cases unchanged. The user
code must not override iter/next/StopIteration or inspect local bindings.
"""

from __future__ import annotations

import ast
import copy
import io
import tokenize
from dataclasses import dataclass


@dataclass(frozen=True)
class _Edit:
    start: int
    end: int
    replacement: bytes


_SENSITIVE_NAMES = {
    "iter", "next", "StopIteration", "locals", "globals", "vars", "dir",
    "eval", "exec", "compile", "__import__",
}


def _has_sensitive_bindings(tree: ast.AST) -> bool:
    """Fail closed when added builtins could resolve to another object."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id in {"iter", "next", "StopIteration"} and isinstance(
                node.ctx, (ast.Store, ast.Del)
            ):
                return True
            if node.id in {"locals", "globals", "vars", "dir", "eval", "exec", "compile", "__import__"}:
                return True
        elif isinstance(node, ast.arg) and node.arg in _SENSITIVE_NAMES:
            return True
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in _SENSITIVE_NAMES:
                return True
        elif isinstance(node, ast.alias):
            alias = node.asname or node.name.split(".", 1)[0]
            if alias in _SENSITIVE_NAMES or node.name == "*":
                return True
        elif isinstance(node, ast.ExceptHandler) and node.name in _SENSITIVE_NAMES:
            return True
        elif isinstance(node, ast.MatchAs) and node.name in _SENSITIVE_NAMES:
            return True
        elif isinstance(node, ast.MatchStar) and node.name in _SENSITIVE_NAMES:
            return True
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            if set(node.names) & _SENSITIVE_NAMES:
                return True
    return False


def _comments(source: str) -> set[int]:
    return {
        token.start[0]
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
    }


def _fresh_name(used: set[str], stem: str) -> str:
    suffix = 0
    while True:
        value = f"__capstone_{stem}_{suffix}"
        suffix += 1
        if value not in used:
            used.add(value)
            return value


def _name(identifier: str, context: ast.expr_context = None) -> ast.Name:
    return ast.Name(id=identifier, ctx=context or ast.Load())


def _convert_node(
    node: ast.For, iter_name: str, value_name: str, finished_name: str | None
) -> ast.Module:
    """Make a statement block that follows Python iterator semantics."""
    assign_iterator = ast.Assign(
        targets=[_name(iter_name, ast.Store())],
        value=ast.Call(func=_name("iter"), args=[copy.deepcopy(node.iter)], keywords=[]),
    )
    next_item = ast.Assign(
        targets=[_name(value_name, ast.Store())],
        value=ast.Call(func=_name("next"), args=[_name(iter_name)], keywords=[]),
    )
    bind_target = ast.Assign(
        targets=[copy.deepcopy(node.target)], value=_name(value_name)
    )
    handler_body: list[ast.stmt] = [ast.Break()]
    if finished_name is not None:
        handler_body.insert(
            0,
            ast.Assign(targets=[_name(finished_name, ast.Store())], value=ast.Constant(True)),
        )

    pull = ast.Try(
        body=[next_item],
        handlers=[ast.ExceptHandler(type=_name("StopIteration"), name=None, body=handler_body)],
        orelse=[],
        finalbody=[],
    )
    loop = ast.While(
        test=ast.Constant(True),
        body=[pull, bind_target, *copy.deepcopy(node.body)],
        orelse=[],
    )
    guarded: list[ast.stmt] = [loop]
    cleanup: list[ast.expr] = [
        _name(iter_name, ast.Del()), _name(value_name, ast.Del())
    ]
    result: list[ast.stmt] = [
        assign_iterator,
        ast.Assign(
            targets=[_name(value_name, ast.Store())], value=ast.Constant(None)
        ),
    ]
    if finished_name is not None:
        result.append(
            ast.Assign(targets=[_name(finished_name, ast.Store())], value=ast.Constant(False))
        )
        guarded.append(
            ast.If(test=_name(finished_name), body=copy.deepcopy(node.orelse), orelse=[])
        )
        cleanup.append(_name(finished_name, ast.Del()))
    # The temporary value is initialized before the loop, even for empty
    # inputs, so it can always be deleted without introducing NameError.
    result.append(
        ast.Try(body=guarded, handlers=[], orelse=[], finalbody=[ast.Delete(targets=cleanup)])
    )
    module = ast.Module(body=result, type_ignores=[])
    ast.fix_missing_locations(module)
    return module


def _statement_span(source: str, node: ast.For) -> tuple[int, int, str] | None:
    """Accept a complete statement; avoid adjacent semicolon statements."""
    if node.end_lineno is None or node.end_col_offset is None:
        return None
    lines = source.splitlines(keepends=True)
    if node.lineno > len(lines) or node.end_lineno > len(lines):
        return None
    first = lines[node.lineno - 1].encode("utf-8")
    last = lines[node.end_lineno - 1].encode("utf-8")
    left = first[:node.col_offset]
    if left.strip() or last[node.end_col_offset:].strip():
        return None
    try:
        indent = left.decode("utf-8")
    except UnicodeDecodeError:
        return None
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line.encode("utf-8")))
    return (
        offsets[node.lineno - 1] + node.col_offset,
        offsets[node.end_lineno - 1] + node.end_col_offset,
        indent,
    )


def _rewrite_span(source: str, node: ast.For, module: ast.Module) -> _Edit | None:
    span = _statement_span(source, node)
    if span is None:
        return None
    start, end, indent = span
    replacement = ast.unparse(module)
    lines = replacement.split("\n")
    # The original leading indentation is retained before the edit begins.
    replacement = ("\n" + indent).join(lines)
    return _Edit(start, end, replacement.encode("utf-8"))


def transform_for_to_while_style(code: str) -> str:
    """Convert ordinary synchronous for loops, including break/continue/else.

    Dynamic iteration is preserved: the original iterable expression runs
    once, and items are retrieved one at a time from the same iterator.
    Comments within the transformed loop, async for, introspection-sensitive
    code, and syntactically unsupported cases are left unchanged.
    """
    try:
        tree = ast.parse(code)
        if _has_sensitive_bindings(tree):
            return code
        commented = _comments(code)
        used = {
            child.id for child in ast.walk(tree)
            if isinstance(child, ast.Name)
        }
        used |= {
            child.arg for child in ast.walk(tree)
            if isinstance(child, ast.arg)
        }
        used |= {
            child.name for child in ast.walk(tree)
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        used |= {
            name for child in ast.walk(tree)
            if isinstance(child, (ast.Global, ast.Nonlocal))
            for name in child.names
        }
        used |= {
            (child.asname or child.name.split(".", 1)[0])
            for child in ast.walk(tree)
            if isinstance(child, ast.alias)
        }
        edits: list[_Edit] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.For):
                continue
            if any(node.lineno <= line <= node.end_lineno for line in commented):
                continue
            # A rewritten parent already contains its untouched nested loops.
            span = _statement_span(code, node)
            if span is None:
                continue
            start, end, _ = span
            if any(start < existing.end and existing.start < end for existing in edits):
                continue
            iterator = _fresh_name(used, "iterator")
            value = _fresh_name(used, "pulled")
            finished = _fresh_name(used, "finished") if node.orelse else None
            block = _convert_node(node, iterator, value, finished)
            edit = _rewrite_span(code, node, block)
            if edit is not None:
                edits.append(edit)

        if not edits:
            return code
        result = code.encode("utf-8")
        for item in sorted(edits, key=lambda edit: edit.start, reverse=True):
            result = result[:item.start] + item.replacement + result[item.end:]
        updated = result.decode("utf-8")
        ast.parse(updated)
        return updated
    except (SyntaxError, tokenize.TokenError, ValueError, UnicodeError, TypeError):
        return code
