"""Remove comments and standalone literal-string statements from displayed style output.

This is intentionally separate from analysis-only comment filtering. It edits
source spans rather than unparsing a whole module, preserving formatting and
actual string values. Plain string statements (including docstrings) are
removed by user request; that can change __doc__ and introspection behavior.
"""
from __future__ import annotations

import ast
import io
import tokenize


def _standalone_string(statement: ast.AST) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def _byte_offsets(lines: list[str]) -> list[int]:
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line.encode('utf-8')))
    return offsets


def _blank_span(source: bytes, *, insert_pass: bool) -> bytes:
    # Newlines stay in their original positions, preserving line numbers/CRLF.
    replacement = bytearray(32 if b not in (10, 13) else b for b in source)
    if insert_pass:
        # A lone string statement is a complete Python suite. Replacing it
        # with pass avoids leaving an empty function/class/if/except body.
        first_newline = next((i for i, b in enumerate(replacement) if b in (10, 13)), len(replacement))
        if first_newline >= 4:
            replacement[:4] = b'pass'
        else:
            # The source span might be a 3-character literal: 'x'. Widen the
            # edit. Changes are applied right-to-left, preserving other edits.
            return b'pass' + bytes(replacement[first_newline:])
    return bytes(replacement)


def strip_style_output_comments(code: str) -> str:
    """Remove # comments and independent literal strings, never data strings.

    Returns original source for syntactically invalid inputs. The route already
    handles invalid Python. Does not execute submitted/user code.
    """
    if not isinstance(code, str):
        raise TypeError('code must be a Python source string')
    if not code:
        return code

    try:
        tree = ast.parse(code)
        lines = code.splitlines(keepends=True)
        byte_starts = _byte_offsets(lines)
        source = code.encode('utf-8')
        changes: list[tuple[int, int, bytes]] = []

        # Parent suite lists determine which removals need a pass placeholder.
        requires_pass: set[int] = set()
        for parent in ast.walk(tree):
            for _field, value in ast.iter_fields(parent):
                if not (isinstance(value, list) and value and
                        all(isinstance(item, ast.stmt) for item in value)):
                    continue
                # A standalone string adjacent to another statement on the
                # same physical line needs pass; blanking it would leave a
                # leading/trailing semicolon and invalidate Python.
                for index, item in enumerate(value):
                    if not _standalone_string(item):
                        continue
                    adjacent = [other for j, other in enumerate(value) if j != index]
                    if any(other.lineno == item.lineno for other in adjacent):
                        requires_pass.add(id(item))
                if not isinstance(parent, ast.Module) and all(
                    _standalone_string(item) for item in value
                ):
                    requires_pass.add(id(value[0]))

        for node in ast.walk(tree):
            if not _standalone_string(node):
                continue
            start = byte_starts[node.lineno - 1] + node.col_offset
            end = byte_starts[node.end_lineno - 1] + node.end_col_offset
            # Replace only the standalone expression. The enclosing indentation,
            # semicolons, comments and other statements are not touched.
            changes.append((start, end, _blank_span(
                source[start:end], insert_pass=(id(node) in requires_pass),
            )))

        for token in tokenize.generate_tokens(io.StringIO(code).readline):
            if token.type != tokenize.COMMENT:
                continue
            line_number = token.start[0] - 1
            line = lines[line_number]
            start = byte_starts[line_number] + len(line[:token.start[1]].encode('utf-8'))
            end = byte_starts[line_number] + len(line[:token.end[1]].encode('utf-8'))
            changes.append((start, end, b' ' * (end - start)))

        if not changes:
            return code
        result = source
        previous_start = len(source) + 1
        for start, end, replacement in sorted(changes, key=lambda t: t[0], reverse=True):
            if end > previous_start:
                return code  # Unexpected overlapping spans: fail closed.
            result = result[:start] + replacement + result[end:]
            previous_start = start
        output = result.decode('utf-8')
        ast.parse(output)
        return output
    except (SyntaxError, ValueError, UnicodeError, IndentationError, tokenize.TokenError, IndexError):
        return code
