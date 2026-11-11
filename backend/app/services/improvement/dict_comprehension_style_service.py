
"""Convert a narrow, side-effect-free dictionary accumulation pattern.

A new empty dictionary followed immediately by a simple for loop can become
one dictionary comprehension. Ambiguous expressions and observable loop-target
bindings remain unchanged.
"""

import ast
import io
import tokenize


def _simple_expression(node: ast.AST) -> bool:
    """Allow a small subset without calls, attribute access or mutation."""
    if isinstance(node, ast.Name):
        return isinstance(node.ctx, ast.Load)

    if isinstance(node, ast.Constant):
        return type(node.value) in (str, int, float, bool, type(None))

    if isinstance(node, ast.UnaryOp):
        return isinstance(node.op, (ast.Not, ast.UAdd, ast.USub)) and (
            _simple_expression(node.operand)
        )

    if isinstance(node, ast.BinOp):
        return isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Mod)) and (
            _simple_expression(node.left)
            and _simple_expression(node.right)
        )

    if isinstance(node, ast.BoolOp):
        return isinstance(node.op, (ast.And, ast.Or)) and all(
            _simple_expression(value) for value in node.values
        )

    if isinstance(node, ast.Compare):
        return all(
            isinstance(
                op,
                (
                    ast.Eq,
                    ast.NotEq,
                    ast.Lt,
                    ast.LtE,
                    ast.Gt,
                    ast.GtE,
                    ast.In,
                    ast.NotIn,
                ),
            )
            for op in node.ops
        ) and all(
            _simple_expression(value)
            for value in (node.left, *node.comparators)
        )

    return False


def _reads_name(node: ast.AST, name: str) -> bool:
    return any(
        isinstance(child, ast.Name)
        and isinstance(child.ctx, ast.Load)
        and child.id == name
        for child in ast.walk(node)
    )


def _name_observed_elsewhere(
    scope: ast.AST,
    first: ast.Assign,
    second: ast.For,
    name: str,
) -> bool:
    """A comprehension does not leak its iteration variable to the scope."""
    excluded = {
        id(node)
        for root in (first, second)
        for node in ast.walk(root)
    }

    for node in ast.walk(scope):
        if id(node) in excluded:
            continue

        if isinstance(node, ast.Name) and node.id == name:
            return True

        if isinstance(node, ast.arg) and node.arg == name:
            return True

        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            if node.name == name:
                return True

        if isinstance(node, ast.alias):
            if (node.asname or node.name.split(".")[0]) == name:
                return True

        if isinstance(node, (ast.Global, ast.Nonlocal)):
            if name in node.names:
                return True

        if isinstance(node, ast.ExceptHandler) and node.name == name:
            return True

        if isinstance(node, (ast.MatchAs, ast.MatchStar)):
            if node.name == name:
                return True

        if isinstance(node, ast.MatchMapping) and node.rest == name:
            return True

    return False


def _unsafe_scope(scope: ast.AST, names: set[str]) -> bool:
    """Reject global/nonlocal bindings and dynamic scope inspection."""
    for node in ast.walk(scope):
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            if names.intersection(node.names):
                return True

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {
                "locals",
                "globals",
                "vars",
                "eval",
                "exec",
                "dir",
            }:
                return True

    return False


class _DictionaryComprehensionFinder(ast.NodeVisitor):
    def __init__(self, source: str, commented_lines: set[int]):
        self.source = source
        self.commented_lines = commented_lines
        self.edits: list[tuple[ast.Assign, ast.For, str]] = []

    def _inspect_body(
        self,
        body: list[ast.stmt],
        scope: ast.AST,
    ) -> None:
        for index in range(len(body) - 1):
            first, second = body[index:index + 2]

            if not (
                isinstance(first, ast.Assign)
                and isinstance(second, ast.For)
            ):
                continue

            if (
                len(first.targets) != 1
                or not isinstance(first.targets[0], ast.Name)
            ):
                continue

            result_name = first.targets[0].id

            if not isinstance(first.value, ast.Dict) or first.value.keys:
                continue

            if not isinstance(second.target, ast.Name):
                continue

            item_name = second.target.id

            if item_name == result_name:
                continue

            if not isinstance(second.iter, ast.Name):
                continue

            if second.iter.id in {result_name, item_name}:
                continue

            if second.orelse or len(second.body) != 1:
                continue

            if (
                first.lineno != first.end_lineno
                or second.lineno != first.end_lineno + 1
                or first.col_offset != second.col_offset
            ):
                continue

            statement = second.body[0]
            condition = None

            if isinstance(statement, ast.If):
                if statement.orelse or len(statement.body) != 1:
                    continue

                condition = statement.test
                statement = statement.body[0]

            if (
                not isinstance(statement, ast.Assign)
                or len(statement.targets) != 1
            ):
                continue

            target = statement.targets[0]

            if not (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == result_name
            ):
                continue

            key = target.slice
            value = statement.value

            if not (
                _simple_expression(key)
                and _simple_expression(value)
            ):
                continue

            if (
                condition is not None
                and not _simple_expression(condition)
            ):
                continue

            if not _reads_name(key, item_name):
                continue

            if any(
                _reads_name(expr, result_name)
                for expr in (second.iter, key, value, condition)
                if expr is not None
            ):
                continue

            if _name_observed_elsewhere(
                scope,
                first,
                second,
                item_name,
            ):
                continue

            if _unsafe_scope(scope, {result_name, item_name}):
                continue

            if any(
                first.lineno <= line <= second.end_lineno
                for line in self.commented_lines
            ):
                continue

            suffix = (
                f" if {ast.unparse(condition)}"
                if condition is not None
                else ""
            )

            replacement = (
                f"{result_name} = "
                f"{{{ast.unparse(key)}: {ast.unparse(value)} "
                f"for {item_name} in {ast.unparse(second.iter)}{suffix}}}"
            )

            self.edits.append(
                (first, second, replacement)
            )

    def visit_Module(self, node: ast.Module) -> None:
        self._inspect_body(node.body, node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._inspect_body(node.body, node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> None:
        # Preserve coroutine and async function behavior.
        return


def transform_to_dict_comprehension_style(code: str) -> str:
    """Rewrite only adjacent, structurally simple dictionary accumulation."""
    try:
        tree = ast.parse(code)

        commented_lines = {
            token.start[0]
            for token in tokenize.generate_tokens(
                io.StringIO(code).readline
            )
            if token.type == tokenize.COMMENT
        }

        finder = _DictionaryComprehensionFinder(
            code,
            commented_lines,
        )

        finder.visit(tree)

        if not finder.edits:
            return code

        lines = code.splitlines(keepends=True)
        byte_offsets = [0]

        for line in lines:
            byte_offsets.append(
                byte_offsets[-1] + len(line.encode("utf-8"))
            )

        output = code.encode("utf-8")
        edits = []

        for first, last, replacement in finder.edits:
            if (
                last.end_lineno is None
                or last.end_col_offset is None
            ):
                continue

            start = (
                byte_offsets[first.lineno - 1]
                + first.col_offset
            )

            end = (
                byte_offsets[last.end_lineno - 1]
                + last.end_col_offset
            )

            edits.append(
                (start, end, replacement.encode("utf-8"))
            )

        for start, end, replacement in sorted(
            edits,
            reverse=True,
        ):
            output = (
                output[:start]
                + replacement
                + output[end:]
            )

        transformed = output.decode("utf-8")
        ast.parse(transformed)

        return transformed

    except (
        SyntaxError,
        tokenize.TokenError,
        UnicodeError,
        ValueError,
    ):
        return code
