
"""Conservative conversion of fresh list.sort() patterns into sorted().

Only a new list made from primitive literal values and sorted on the next
physical line can be rewritten. Unknown objects, aliases, custom keys, and
possible shadows of the sorted builtin remain unchanged.
"""

import ast
import io
import tokenize


def _literal_kind(node: ast.AST) -> str | None:
    """Recognize literal values with predictable built-in comparisons."""
    if isinstance(node, ast.Constant):
        if type(node.value) in (int, float):
            return "number"
        if type(node.value) is str:
            return "string"

    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, (ast.UAdd, ast.USub))
        and isinstance(node.operand, ast.Constant)
        and type(node.operand.value) in (int, float)
    ):
        return "number"

    return None


def _sorted_name_may_be_shadowed(tree: ast.AST) -> bool:
    """Fail closed if user code mentions a possible sorted binding."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in {"sorted", "__builtins__"}:
            return True

        if isinstance(node, ast.arg) and node.arg == "sorted":
            return True

        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            if node.name == "sorted":
                return True

        if isinstance(node, ast.alias):
            if (node.asname or node.name.split(".")[0]) == "sorted":
                return True

        if isinstance(node, (ast.Global, ast.Nonlocal)):
            if "sorted" in node.names:
                return True

        if isinstance(node, ast.ExceptHandler) and node.name == "sorted":
            return True

        if isinstance(node, (ast.MatchAs, ast.MatchStar)):
            if node.name == "sorted":
                return True

        if isinstance(node, ast.MatchMapping) and node.rest == "sorted":
            return True

        if isinstance(node, ast.alias) and node.name == "*":
            return True

    return False


class _FreshListSortFinder(ast.NodeVisitor):
    """Find adjacent literal-list assignment and in-place sort pairs."""

    def __init__(self, source: str, comment_lines: set[int]):
        self.source = source
        self.comment_lines = comment_lines
        self.edits: list[tuple[ast.Assign, ast.Expr, str]] = []

    @staticmethod
    def _sort_parameters(call: ast.Call) -> str | None:
        """Allow default sorting or a literal boolean reverse argument."""
        if call.args:
            return None

        if not call.keywords:
            return ""

        if len(call.keywords) != 1:
            return None

        keyword = call.keywords[0]

        if keyword.arg != "reverse":
            return None

        if not (
            isinstance(keyword.value, ast.Constant)
            and type(keyword.value.value) is bool
        ):
            return None

        return f", reverse={keyword.value.value}"

    @staticmethod
    def _has_global_or_nonlocal(
        body: list[ast.stmt],
        name: str,
    ) -> bool:
        return any(
            isinstance(node, (ast.Global, ast.Nonlocal))
            and name in node.names
            for stmt in body
            for node in ast.walk(stmt)
        )

    def _inspect_body(self, body: list[ast.stmt]) -> None:
        for index in range(len(body) - 1):
            first = body[index]
            second = body[index + 1]

            if not (
                isinstance(first, ast.Assign)
                and isinstance(second, ast.Expr)
            ):
                continue

            if (
                len(first.targets) != 1
                or not isinstance(first.targets[0], ast.Name)
            ):
                continue

            name = first.targets[0].id

            if name == "sorted":
                continue

            if not isinstance(first.value, ast.List):
                continue

            if len(first.value.elts) < 2:
                continue

            kinds = {
                _literal_kind(item)
                for item in first.value.elts
            }

            if (
                not kinds <= {"string"}
                and not kinds <= {"number"}
            ):
                continue

            if not isinstance(second.value, ast.Call):
                continue

            call = second.value

            if not (
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "sort"
            ):
                continue

            if not (
                isinstance(call.func.value, ast.Name)
                and call.func.value.id == name
            ):
                continue

            parameters = self._sort_parameters(call)

            if parameters is None:
                continue

            # Both statements must be on consecutive physical lines.
            if (
                first.end_lineno != first.lineno
                or second.end_lineno != second.lineno
                or second.lineno != first.lineno + 1
                or second.col_offset != first.col_offset
            ):
                continue

            # Do not delete source comments in the rewritten span.
            if any(
                first.lineno <= line_number <= second.end_lineno
                for line_number in self.comment_lines
            ):
                continue

            if self._has_global_or_nonlocal(body, name):
                continue

            literal = ast.get_source_segment(
                self.source,
                first.value,
            )

            if literal is None:
                continue

            replacement = (
                f"{name} = sorted({literal}{parameters})"
            )

            self.edits.append(
                (first, second, replacement)
            )

    def generic_visit(self, node: ast.AST) -> None:
        # Inspect statement blocks without changing their AST nodes.
        for field in ("body", "orelse", "finalbody"):
            body = getattr(node, field, None)

            if (
                isinstance(body, list)
                and body
                and all(isinstance(stmt, ast.stmt) for stmt in body)
            ):
                self._inspect_body(body)

        super().generic_visit(node)


def transform_to_sort_style(code: str) -> str:
    """
    Rewrite a freshly created literal list followed by list.sort().

    Supported:
        values = [3, 1, 2]
        values.sort()

    Output:
        values = sorted([3, 1, 2])

    Additional support:
        values.sort(reverse=True)
        values.sort(reverse=False)

    Unsupported:
        - Function parameters and unknown list objects
        - Custom sort keys
        - Possible shadowing of sorted()
        - Mixed-type or non-primitive values
        - Comments inside the replacement span
        - Nonadjacent or multiline statement patterns

    Source-level edits preserve unrelated code and comments.
    """

    try:
        tree = ast.parse(code)

        if _sorted_name_may_be_shadowed(tree):
            return code

        comment_lines = {
            token.start[0]
            for token in tokenize.generate_tokens(
                io.StringIO(code).readline
            )
            if token.type == tokenize.COMMENT
        }

        finder = _FreshListSortFinder(
            code,
            comment_lines,
        )
        finder.visit(tree)

        if not finder.edits:
            return code

        lines = code.splitlines(keepends=True)

        offsets = [0]

        for line in lines:
            offsets.append(
                offsets[-1] + len(line.encode("utf-8"))
            )

        output = code.encode("utf-8")

        edits: list[tuple[int, int, bytes]] = []

        for first, last, replacement in finder.edits:
            if (
                last.end_lineno is None
                or last.end_col_offset is None
            ):
                continue

            start = (
                offsets[first.lineno - 1]
                + first.col_offset
            )

            end = (
                offsets[last.end_lineno - 1]
                + last.end_col_offset
            )

            edits.append(
                (start, end, replacement.encode("utf-8"))
            )

        # Apply edits backwards so earlier byte offsets stay valid.
        for start, end, replacement in sorted(
            edits,
            key=lambda edit: edit[0],
            reverse=True,
        ):
            output = (
                output[:start]
                + replacement
                + output[end:]
            )

        transformed = output.decode("utf-8")

        # The resulting code must remain valid Python.
        ast.parse(transformed)

        return transformed

    except (
        SyntaxError,
        tokenize.TokenError,
        UnicodeError,
        ValueError,
    ):
        return code
