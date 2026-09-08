import ast


class ResourceStyleTransformer(ast.NodeTransformer):
    """
    파일/자원 관리 스타일 변환기.

    목표:
    - 직접 open 후 close하는 단순 패턴을 with open 구조로 변환합니다.
    - 실행 결과가 달라질 가능성이 있는 복잡한 패턴은 변환하지 않습니다.

    지원:
    1. file = open(path, "r") + data = file.read() + file.close()
    2. file = open(path, "w") + file.write(data) + file.close()
    3. file = open(path) + 여러 단순 작업 + file.close()
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
            transformed, consumed = self._try_transform_open_close_pattern(body, i)

            if transformed is not None:
                new_body.append(transformed)
                self.changed = True
                i += consumed
                continue

            new_body.append(body[i])
            i += 1

        return new_body

    def _try_transform_open_close_pattern(self, body: list[ast.stmt], start_index: int):
        if start_index + 2 >= len(body):
            return None, 0

        open_stmt = body[start_index]

        if not isinstance(open_stmt, ast.Assign):
            return None, 0

        if len(open_stmt.targets) != 1 or not isinstance(open_stmt.targets[0], ast.Name):
            return None, 0

        file_var_name = open_stmt.targets[0].id

        if not isinstance(open_stmt.value, ast.Call):
            return None, 0

        open_call = open_stmt.value

        if not isinstance(open_call.func, ast.Name) or open_call.func.id != "open":
            return None, 0

        close_index = self._find_close_index(body, start_index + 1, file_var_name)

        if close_index is None:
            return None, 0

        work_body = body[start_index + 1:close_index]

        if not work_body:
            return None, 0

        if not self._is_safe_file_work_body(work_body, file_var_name):
            return None, 0

        with_node = ast.With(
            items=[
                ast.withitem(
                    context_expr=open_call,
                    optional_vars=ast.Name(id=file_var_name, ctx=ast.Store()),
                )
            ],
            body=work_body,
            type_comment=None,
        )

        consumed = close_index - start_index + 1

        return ast.fix_missing_locations(with_node), consumed

    def _find_close_index(self, body: list[ast.stmt], start_index: int, file_var_name: str):
        for index in range(start_index, len(body)):
            if self._is_close_call(body[index], file_var_name):
                return index

        return None

    def _is_close_call(self, stmt: ast.stmt, file_var_name: str) -> bool:
        return (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Attribute)
            and stmt.value.func.attr == "close"
            and isinstance(stmt.value.func.value, ast.Name)
            and stmt.value.func.value.id == file_var_name
        )

    def _is_safe_file_work_body(self, body: list[ast.stmt], file_var_name: str) -> bool:
        for stmt in body:
            if isinstance(stmt, (ast.Return, ast.Yield, ast.YieldFrom, ast.Raise, ast.Break, ast.Continue)):
                return False

            if not self._uses_file_variable(stmt, file_var_name):
                continue

        return True

    def _uses_file_variable(self, node: ast.AST, file_var_name: str) -> bool:
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id == file_var_name:
                return True

        return False


def normalize_code(code: str) -> str:
    try:
        return ast.unparse(ast.parse(code)).strip()
    except Exception:
        return code.strip()


def transform_resource_style(code: str) -> str:
    try:
        tree = ast.parse(code)
        transformer = ResourceStyleTransformer()
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