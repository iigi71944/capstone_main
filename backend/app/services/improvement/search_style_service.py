import ast


class SearchStyleTransformer(ast.NodeTransformer):
    """
    검색/탐색 중심 구조 변환기.

    목표:
    - 실행 결과가 달라질 위험이 낮은 단순 탐색 패턴만 변환합니다.
    - for + if + return 패턴을 next(...) 또는 any(...) 구조로 정리합니다.

    지원:
    1. for item in items:
           if condition:
               return item
       return None

       ->
       return next((item for item in items if condition), None)

    2. for item in items:
           if condition:
               return True
       return False

       ->
       return any(condition for item in items)
    """

    def __init__(self):
        self.changed = False

    def visit_Module(self, node: ast.Module):
        self.generic_visit(node)
        node.body = self._transform_statement_list(node.body)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.generic_visit(node)
        node.body = self._transform_statement_list(node.body)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.generic_visit(node)
        node.body = self._transform_statement_list(node.body)
        return node

    def _transform_statement_list(self, body: list[ast.stmt]) -> list[ast.stmt]:
        new_body = []
        i = 0

        while i < len(body):
            if i + 1 < len(body):
                next_return = self._try_transform_next_pattern(body[i], body[i + 1])
                if next_return is not None:
                    new_body.append(next_return)
                    self.changed = True
                    i += 2
                    continue

                any_return = self._try_transform_any_pattern(body[i], body[i + 1])
                if any_return is not None:
                    new_body.append(any_return)
                    self.changed = True
                    i += 2
                    continue

            new_body.append(body[i])
            i += 1

        return new_body

    def _try_transform_next_pattern(self, for_stmt: ast.stmt, return_stmt: ast.stmt):
        parsed = self._parse_for_if_return(for_stmt)

        if parsed is None:
            return None

        loop_target, loop_iter, condition, inner_return = parsed

        if not isinstance(return_stmt, ast.Return):
            return None

        if not isinstance(return_stmt.value, ast.Constant) or return_stmt.value.value is not None:
            return None

        if not isinstance(loop_target, ast.Name):
            return None

        if not isinstance(inner_return.value, ast.Name):
            return None

        if inner_return.value.id != loop_target.id:
            return None

        generator = ast.GeneratorExp(
            elt=ast.Name(id=loop_target.id, ctx=ast.Load()),
            generators=[
                ast.comprehension(
                    target=loop_target,
                    iter=loop_iter,
                    ifs=[condition],
                    is_async=0,
                )
            ],
        )

        new_return = ast.Return(
            value=ast.Call(
                func=ast.Name(id="next", ctx=ast.Load()),
                args=[
                    generator,
                    ast.Constant(value=None),
                ],
                keywords=[],
            )
        )

        return ast.fix_missing_locations(new_return)

    def _try_transform_any_pattern(self, for_stmt: ast.stmt, return_stmt: ast.stmt):
        parsed = self._parse_for_if_return(for_stmt)

        if parsed is None:
            return None

        loop_target, loop_iter, condition, inner_return = parsed

        if not isinstance(return_stmt, ast.Return):
            return None

        if not isinstance(inner_return.value, ast.Constant) or inner_return.value.value is not True:
            return None

        if not isinstance(return_stmt.value, ast.Constant) or return_stmt.value.value is not False:
            return None

        generator = ast.GeneratorExp(
            elt=condition,
            generators=[
                ast.comprehension(
                    target=loop_target,
                    iter=loop_iter,
                    ifs=[],
                    is_async=0,
                )
            ],
        )

        new_return = ast.Return(
            value=ast.Call(
                func=ast.Name(id="any", ctx=ast.Load()),
                args=[generator],
                keywords=[],
            )
        )

        return ast.fix_missing_locations(new_return)

    def _parse_for_if_return(self, for_stmt: ast.stmt):
        if not isinstance(for_stmt, ast.For):
            return None

        if for_stmt.orelse:
            return None

        if len(for_stmt.body) != 1:
            return None

        if_stmt = for_stmt.body[0]

        if not isinstance(if_stmt, ast.If):
            return None

        if if_stmt.orelse:
            return None

        if len(if_stmt.body) != 1:
            return None

        inner_return = if_stmt.body[0]

        if not isinstance(inner_return, ast.Return):
            return None

        return for_stmt.target, for_stmt.iter, if_stmt.test, inner_return


def normalize_code(code: str) -> str:
    try:
        return ast.unparse(ast.parse(code)).strip()
    except Exception:
        return code.strip()


def transform_search_style(code: str) -> str:
    try:
        tree = ast.parse(code)

        transformer = SearchStyleTransformer()
        transformed_tree = transformer.visit(tree)

        ast.fix_missing_locations(transformed_tree)

        if not transformer.changed:
            return code

        transformed_code = ast.unparse(transformed_tree)

        if normalize_code(code) == normalize_code(transformed_code):
            return code

        return transformed_code

    except Exception:
        return code