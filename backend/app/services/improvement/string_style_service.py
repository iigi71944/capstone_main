import ast


STRING_CHAINABLE_METHODS = {
    "strip",
    "lstrip",
    "rstrip",
    "lower",
    "upper",
    "title",
    "capitalize",
    "replace",
}


class StringStyleTransformer(ast.NodeTransformer):
    """
    문자열 처리 중심 구조 변환기.

    목표:
    - 실행 결과가 달라질 가능성이 낮은 단순 문자열 처리 패턴만 변환합니다.
    - 같은 변수에 연속으로 적용되는 문자열 메서드 호출을 메서드 체인으로 정리합니다.

    예:
    name = name.strip()
    name = name.title()

    ->
    name = name.strip().title()
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
            chained_stmt, consumed = self._try_transform_string_chain(body, i)

            if chained_stmt is not None:
                new_body.append(chained_stmt)
                self.changed = True
                i += consumed
                continue

            new_body.append(body[i])
            i += 1

        return new_body

    def _try_transform_string_chain(self, body: list[ast.stmt], start_index: int):
        first_info = self._parse_string_method_assignment(body[start_index])

        if first_info is None:
            return None, 0

        target_name, current_expr = first_info
        consumed = 1
        current_index = start_index + 1

        while current_index < len(body):
            next_info = self._parse_string_method_assignment(body[current_index])

            if next_info is None:
                break

            next_target_name, next_call = next_info

            if next_target_name != target_name:
                break

            if not self._call_uses_variable(next_call, target_name):
                break

            current_expr = self._replace_receiver_with_expr(
                call_node=next_call,
                new_receiver=current_expr,
            )

            consumed += 1
            current_index += 1

        if consumed < 2:
            return None, 0

        new_assign = ast.Assign(
            targets=[ast.Name(id=target_name, ctx=ast.Store())],
            value=current_expr,
        )

        return ast.fix_missing_locations(new_assign), consumed

    def _parse_string_method_assignment(self, stmt: ast.stmt):
        if not isinstance(stmt, ast.Assign):
            return None

        if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
            return None

        target_name = stmt.targets[0].id

        if not isinstance(stmt.value, ast.Call):
            return None

        call = stmt.value

        if not isinstance(call.func, ast.Attribute):
            return None

        if call.func.attr not in STRING_CHAINABLE_METHODS:
            return None

        return target_name, call

    def _call_uses_variable(self, call_node: ast.Call, variable_name: str) -> bool:
        return (
            isinstance(call_node.func, ast.Attribute)
            and isinstance(call_node.func.value, ast.Name)
            and call_node.func.value.id == variable_name
        )

    def _replace_receiver_with_expr(self, call_node: ast.Call, new_receiver: ast.expr) -> ast.Call:
        if not isinstance(call_node.func, ast.Attribute):
            return call_node

        new_call = ast.Call(
            func=ast.Attribute(
                value=new_receiver,
                attr=call_node.func.attr,
                ctx=ast.Load(),
            ),
            args=call_node.args,
            keywords=call_node.keywords,
        )

        return ast.fix_missing_locations(new_call)


def normalize_code(code: str) -> str:
    try:
        return ast.unparse(ast.parse(code)).strip()
    except Exception:
        return code.strip()


def transform_string_style(code: str) -> str:
    try:
        tree = ast.parse(code)

        transformer = StringStyleTransformer()
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