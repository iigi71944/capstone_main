import ast


class StructuredTransformer(ast.NodeTransformer):
    """
    구조 중심형 변환기.

    목표:
    - 실행 결과가 달라질 가능성이 높은 변환은 하지 않습니다.
    - 새 함수를 임의로 생성하지 않습니다.
    - 원본 코드의 주요 흐름을 유지합니다.
    - 불필요한 else, 중복 return, 중첩 if 등을 정리합니다.

    지원:
    1. if 조건: return True else: return False -> return 조건
    2. if 조건: return False else: return True -> return not 조건
    3. if 내부 return 이후 else 제거
    4. 중첩 if 병합
    5. if True 제거
    6. if False 제거
    """

    def __init__(self):
        self.changed = False

    def visit_If(self, node: ast.If):
        self.generic_visit(node)

        constant_if = self._simplify_constant_if(node)
        if constant_if is not None:
            self.changed = True
            return constant_if

        simplified_return = self._simplify_boolean_return(node)
        if simplified_return is not None:
            self.changed = True
            return ast.fix_missing_locations(simplified_return)

        merged_if = self._merge_nested_if(node)
        if merged_if is not None:
            self.changed = True
            return ast.fix_missing_locations(merged_if)

        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.generic_visit(node)
        node.body = self._remove_unnecessary_else_after_return(node.body)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.generic_visit(node)
        node.body = self._remove_unnecessary_else_after_return(node.body)
        return node

    def _simplify_constant_if(self, node: ast.If):
        if isinstance(node.test, ast.Constant):
            if node.test.value is True:
                return node.body

            if node.test.value is False:
                return node.orelse or []

        return None

    def _simplify_boolean_return(self, node: ast.If):
        if len(node.body) != 1 or len(node.orelse) != 1:
            return None

        body_stmt = node.body[0]
        else_stmt = node.orelse[0]

        if not isinstance(body_stmt, ast.Return):
            return None

        if not isinstance(else_stmt, ast.Return):
            return None

        body_value = body_stmt.value
        else_value = else_stmt.value

        if isinstance(body_value, ast.Constant) and isinstance(else_value, ast.Constant):
            if body_value.value is True and else_value.value is False:
                return ast.Return(value=node.test)

            if body_value.value is False and else_value.value is True:
                return ast.Return(
                    value=ast.UnaryOp(
                        op=ast.Not(),
                        operand=node.test,
                    )
                )

        return None

    def _merge_nested_if(self, node: ast.If):
        if node.orelse:
            return None

        if len(node.body) != 1:
            return None

        inner_if = node.body[0]

        if not isinstance(inner_if, ast.If):
            return None

        if inner_if.orelse:
            return None

        merged_test = ast.BoolOp(
            op=ast.And(),
            values=[
                node.test,
                inner_if.test,
            ],
        )

        return ast.If(
            test=merged_test,
            body=inner_if.body,
            orelse=[],
        )

    def _remove_unnecessary_else_after_return(self, body: list[ast.stmt]) -> list[ast.stmt]:
        new_body = []

        for stmt in body:
            if (
                isinstance(stmt, ast.If)
                and stmt.orelse
                and len(stmt.body) > 0
                and isinstance(stmt.body[-1], ast.Return)
            ):
                new_if = ast.If(
                    test=stmt.test,
                    body=stmt.body,
                    orelse=[],
                )

                new_body.append(ast.fix_missing_locations(new_if))
                new_body.extend(stmt.orelse)
                self.changed = True
            else:
                new_body.append(stmt)

        return new_body


def normalize_code(code: str) -> str:
    try:
        tree = ast.parse(code)
        return ast.unparse(tree).strip()
    except Exception:
        return code.strip()


def transform_to_structured(code: str) -> str:
    try:
        tree = ast.parse(code)

        transformer = StructuredTransformer()
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