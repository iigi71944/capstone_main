
"""Conservative, goal-directed condition and return transformations.

Only rewrite full simple statements. Preserve unrelated source formatting and
comments. Patterns with comments inside the replaced span remain untouched.
"""

from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass


@dataclass(frozen=True)
class _Edit:
    start: int
    end: int
    replacement: bytes


def _expression(source: str, node: ast.AST) -> str | None:
    value = ast.get_source_segment(source, node)
    if not value or "\n" in value or "\r" in value:
        return None
    return value


def _line_offsets(source: str) -> list[int]:
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line.encode("utf-8")))
    return offsets


def _comment_lines(source: str) -> set[int]:
    return {
        token.start[0]
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
    }


def _statement_info(source: str, node: ast.stmt):
    """Return offsets and indentation for a standalone statement only."""
    if node.end_lineno is None or node.end_col_offset is None:
        return None
    lines = source.splitlines(keepends=True)
    if node.lineno > len(lines) or node.end_lineno > len(lines):
        return None
    first_line = lines[node.lineno - 1].encode("utf-8")
    last_line = lines[node.end_lineno - 1].encode("utf-8")
    indent_bytes = first_line[:node.col_offset]
    if indent_bytes.strip() or last_line[node.end_col_offset:].strip():
        return None  # Semicolon statement, inline suite, trailing code, etc.
    try:
        indent = indent_bytes.decode("utf-8")
    except UnicodeError:
        return None
    offsets = _line_offsets(source)
    return (
        offsets[node.lineno - 1] + node.col_offset,
        offsets[node.end_lineno - 1] + node.end_col_offset,
        indent,
    )


def _expand_if_expression(source: str, node: ast.stmt) -> str | None:
    """x = a if c else b -> if c: x = a else: x = b.

    Also supports a return statement containing a conditional expression.
    """
    if isinstance(node, ast.Assign):
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            return None
        target = node.targets[0].id
        expr = node.value
        verb = lambda value: f"{target} = {value}"
    elif isinstance(node, ast.Return):
        expr = node.value
        verb = lambda value: f"return {value}"
    else:
        return None

    if not isinstance(expr, ast.IfExp):
        return None

    test = _expression(source, expr.test)
    yes = _expression(source, expr.body)
    no = _expression(source, expr.orelse)
    info = _statement_info(source, node)
    if not info or test is None or yes is None or no is None:
        return None
    indent = info[2]
    return (
        f"if {test}:\n{indent}    {verb(yes)}\n"
        f"{indent}else:\n{indent}    {verb(no)}"
    )


def _collapse_if_expression(source: str, node: ast.stmt) -> str | None:
    """Turn two branches assigning one name or returning into a ternary."""
    if not isinstance(node, ast.If) or len(node.body) != 1 or len(node.orelse) != 1:
        return None
    if not _is_if_keyword(source, node):
        return None
    yes_stmt, no_stmt = node.body[0], node.orelse[0]
    test = _expression(source, node.test)
    if test is None:
        return None

    if isinstance(yes_stmt, ast.Assign) and isinstance(no_stmt, ast.Assign):
        if (
            len(yes_stmt.targets) != 1
            or len(no_stmt.targets) != 1
            or not isinstance(yes_stmt.targets[0], ast.Name)
            or not isinstance(no_stmt.targets[0], ast.Name)
            or yes_stmt.targets[0].id != no_stmt.targets[0].id
        ):
            return None
        prefix = f"{yes_stmt.targets[0].id} = "
        yes_node, no_node = yes_stmt.value, no_stmt.value
    elif isinstance(yes_stmt, ast.Return) and isinstance(no_stmt, ast.Return):
        if yes_stmt.value is None or no_stmt.value is None:
            return None
        prefix = "return "
        yes_node, no_node = yes_stmt.value, no_stmt.value
    else:
        return None

    yes = _expression(source, yes_node)
    no = _expression(source, no_node)
    if yes is None or no is None:
        return None
    # Parentheses avoid precedence changes in nested Boolean/binary expressions.
    return f"{prefix}({yes}) if ({test}) else ({no})"


def _is_if_keyword(source: str, node: ast.If) -> bool:
    """Do not rewrite an 'elif' node as though it were a standalone 'if'."""
    lines = source.splitlines(keepends=True)
    fragment = lines[node.lineno - 1].encode("utf-8")[node.col_offset:]
    return fragment.startswith(b"if ") or fragment.startswith(b"if(")


def _collapse_boolean_return(source: str, node: ast.stmt) -> str | None:
    """if cond: return True else: return False -> return not not (cond).

    Double negation intentionally preserves bool return *type*, even if the
    condition evaluates to a truthy non-bool value. This also avoids a 'bool'
    name shadowed by caller code.
    """
    if not isinstance(node, ast.If) or len(node.body) != 1 or len(node.orelse) != 1:
        return None
    if not _is_if_keyword(source, node):
        return None
    left, right = node.body[0], node.orelse[0]
    if not isinstance(left, ast.Return) or not isinstance(right, ast.Return):
        return None
    if not isinstance(left.value, ast.Constant) or not isinstance(right.value, ast.Constant):
        return None
    test = _expression(source, node.test)
    if test is None:
        return None
    if left.value.value is True and right.value.value is False:
        return f"return not not ({test})"
    if left.value.value is False and right.value.value is True:
        return f"return not ({test})"
    return None


def _transform(source: str, mode: str) -> str:
    try:
        tree = ast.parse(source)
        comments = _comment_lines(source)
        edits: list[_Edit] = []
        for node in ast.walk(tree):
            if mode == "if" and isinstance(node, (ast.Assign, ast.Return)):
                replacement = _expand_if_expression(source, node)
            elif mode == "expression" and isinstance(node, ast.If):
                replacement = _collapse_if_expression(source, node)
            elif mode == "return" and isinstance(node, ast.If):
                replacement = _collapse_boolean_return(source, node)
            else:
                continue

            if replacement is None:
                continue
            info = _statement_info(source, node)
            if info is None:
                continue
            if any(line in comments for line in range(node.lineno, node.end_lineno + 1)):
                continue
            start, end, _ = info
            if any(start < other.end and other.start < end for other in edits):
                continue
            edits.append(_Edit(start, end, replacement.encode("utf-8")))

        if not edits:
            return source
        updated = source.encode("utf-8")
        for edit in sorted(edits, key=lambda item: item.start, reverse=True):
            updated = updated[:edit.start] + edit.replacement + updated[edit.end:]
        result = updated.decode("utf-8")
        ast.parse(result)
        return result
    except (SyntaxError, tokenize.TokenError, ValueError, UnicodeError):
        return source


def transform_to_if_statement_style(code: str) -> str:
    """Expand simple conditional assignments/returns into if/else blocks."""
    return _transform(code, "if")


def transform_to_conditional_expression_style(code: str) -> str:
    """Collapse simple if/else assignment/return blocks into ternary expressions."""
    return _transform(code, "expression")


def transform_to_boolean_return_style(code: str) -> str:
    """Collapse boolean if/else return blocks into one guaranteed bool return."""
    return _transform(code, "return")
