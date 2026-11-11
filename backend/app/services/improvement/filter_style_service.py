
"""Transform simple conditional list accumulation into a filtered comprehension.

Conservative implementation: unsupported or ambiguous patterns remain unchanged.
No changes to unrelated comprehension, sorting, or aggregation rules.
"""

import ast
import io
import tokenize


class _FilterPatternFinder(ast.NodeVisitor):
    def __init__(self, commented_lines: set[int]):
        self.commented_lines = commented_lines
        self.edits: list[tuple[ast.Assign, ast.For, str]] = []

    @staticmethod
    def _simple_expression(node: ast.AST) -> bool:
        """Allow expressions without calls, assignment, or attribute access."""
        if isinstance(node, ast.Name):
            return isinstance(node.ctx, ast.Load)

        if isinstance(node, ast.Constant):
            return isinstance(
                node.value,
                (str, int, float, bool, type(None)),
            )

        if isinstance(node, ast.UnaryOp):
            return isinstance(
                node.op, (ast.Not, ast.UAdd, ast.USub)
            ) and _FilterPatternFinder._simple_expression(node.operand)

        if isinstance(node, ast.BinOp):
            return isinstance(
                node.op, (ast.Add, ast.Sub, ast.Mult, ast.Mod)
            ) and (
                _FilterPatternFinder._simple_expression(node.left)
                and _FilterPatternFinder._simple_expression(node.right)
            )

        if isinstance(node, ast.BoolOp):
            return isinstance(node.op, (ast.And, ast.Or)) and all(
                _FilterPatternFinder._simple_expression(value)
                for value in node.values
            )

        if isinstance(node, ast.Compare):
            return all(
                isinstance(
                    op,
                    (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE),
                )
                for op in node.ops
            ) and all(
                _FilterPatternFinder._simple_expression(value)
                for value in [node.left, *node.comparators]
            )

        return False

    @staticmethod
    def _reads_name(node: ast.AST, name: str) -> bool:
        return any(
            isinstance(child, ast.Name)
            and isinstance(child.ctx, ast.Load)
            and child.id == name
            for child in ast.walk(node)
        )

    @staticmethod
    def _has_other_target_uses(
        body: list[ast.stmt],
        pair_index: int,
        target_name: str,
    ) -> bool:
        for index, statement in enumerate(body):
            if index in (pair_index, pair_index + 1):
                continue

            if any(
                (isinstance(child, ast.Name) and child.id == target_name)
                or (
                    isinstance(child, (ast.Global, ast.Nonlocal))
                    and target_name in child.names
                )
                for child in ast.walk(statement)
            ):
                return True

        return False

    @staticmethod
    def _has_external_binding(
        body: list[ast.stmt],
        *names: str,
    ) -> bool:
        """Do not transform names declared global or nonlocal in this scope."""
        for statement in body:
            for child in ast.walk(statement):
                if isinstance(child, (ast.Global, ast.Nonlocal)):
                    if set(names) & set(child.names):
                        return True

        return False

    def _inspect_body(self, body: list[ast.stmt]) -> None:
        for index in range(len(body) - 1):
            assign_stmt = body[index]
            loop_stmt = body[index + 1]

            if not (
                isinstance(assign_stmt, ast.Assign)
                and isinstance(loop_stmt, ast.For)
            ):
                continue

            if (
                len(assign_stmt.targets) != 1
                or not isinstance(assign_stmt.targets[0], ast.Name)
            ):
                continue

            result_name = assign_stmt.targets[0].id

            if (
                not isinstance(assign_stmt.value, ast.List)
                or assign_stmt.value.elts
            ):
                continue

            if not isinstance(loop_stmt.target, ast.Name):
                continue

            target_name = loop_stmt.target.id

            if (
                target_name == result_name
                or not isinstance(loop_stmt.iter, ast.Name)
            ):
                continue

            if loop_stmt.iter.id in (target_name, result_name):
                continue

            if loop_stmt.orelse or len(loop_stmt.body) != 1:
                continue

            conditional = loop_stmt.body[0]

            if not isinstance(conditional, ast.If):
                continue

            if conditional.orelse or len(conditional.body) != 1:
                continue

            append_stmt = conditional.body[0]

            if not (
                isinstance(append_stmt, ast.Expr)
                and isinstance(append_stmt.value, ast.Call)
            ):
                continue

            call = append_stmt.value

            if not (
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "append"
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == result_name
                and len(call.args) == 1
                and not call.keywords
            ):
                continue

            condition = conditional.test
            value = call.args[0]

            if not (
                self._simple_expression(condition)
                and self._simple_expression(value)
            ):
                continue

            if not self._reads_name(condition, target_name):
                continue

            if (
                self._reads_name(condition, result_name)
                or self._reads_name(value, result_name)
            ):
                continue

            if self._has_other_target_uses(
                body, index, target_name
            ):
                continue

            if self._has_external_binding(
                body, result_name, target_name
            ):
                continue

            if any(
                assign_stmt.lineno <= comment_line <= loop_stmt.end_lineno
                for comment_line in self.commented_lines
            ):
                continue

            replacement = (
                f"{result_name} = [{ast.unparse(value)} "
                f"for {target_name} in {ast.unparse(loop_stmt.iter)} "
                f"if {ast.unparse(condition)}]"
            )

            self.edits.append(
                (assign_stmt, loop_stmt, replacement)
            )

    def visit_Module(self, node: ast.Module) -> None:
        self._inspect_body(node.body)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._inspect_body(node.body)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> None:
        # Avoid altering coroutine or async scope semantics.
        return


def transform_to_filter_style(code: str) -> str:
    """Convert guarded list.append loops to filtered list comprehensions.

    Uses source-level edits so unrelated formatting and comments survive.
    Skips candidates containing comments and potentially observable
    loop-target usage.
    """
    try:
        tree = ast.parse(code)

        commented_lines = {
            token.start[0]
            for token in tokenize.generate_tokens(
                io.StringIO(code).readline
            )
            if token.type == tokenize.COMMENT
        }

        finder = _FilterPatternFinder(commented_lines)
        finder.visit(tree)

        if not finder.edits:
            return code

        lines = code.splitlines(keepends=True)
        offsets = [0]

        for line in lines:
            offsets.append(
                offsets[-1] + len(line.encode("utf-8"))
            )

        source = code.encode("utf-8")
        replacements: list[tuple[int, int, bytes]] = []

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

            replacements.append(
                (start, end, replacement.encode("utf-8"))
            )

        for start, end, replacement in sorted(
            replacements,
            reverse=True,
        ):
            source = (
                source[:start]
                + replacement
                + source[end:]
            )

        transformed = source.decode("utf-8")
        ast.parse(transformed)

        return transformed

    except (
        SyntaxError,
        tokenize.TokenError,
        UnicodeError,
        ValueError,
    ):
        return code
