import ast


class MappingStyleTransformer(ast.NodeTransformer):
    """
    딕셔너리 기반 매핑 구조 변환기.

    목표:
    - 저장된 스타일에 딕셔너리 기반 매핑 구조 또는 딕셔너리 컴프리헨션 성향이 있을 때,
      대상 코드의 단순 dict 누적 구조를 dict comprehension으로 변환합니다.
    - 실행 결과가 달라질 가능성이 높은 복잡한 패턴은 변환하지 않습니다.
    """

    def __init__(self):
        self.changed = False

    def visit_Module(self, node: ast.Module):
        self.generic_visit(node)
        node.body = self._transform_body(node.body)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.generic_visit(node)
        node.body = self._transform_body(node.body)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.generic_visit(node)
        node.body = self._transform_body(node.body)
        return node

    def _transform_body(self, body: list[ast.stmt]) -> list[ast.stmt]:
        new_body = []
        i = 0

        while i < len(body):
            if i + 1 < len(body):
                transformed = self._dict_loop_to_comprehension(body[i], body[i + 1])

                if transformed is not None:
                    new_body.append(transformed)
                    self.changed = True
                    i += 2
                    continue

            new_body.append(body[i])
            i += 1

        return new_body

    def _dict_loop_to_comprehension(self, assign_stmt: ast.stmt, for_stmt: ast.stmt):
        if not isinstance(assign_stmt, ast.Assign):
            return None

        if len(assign_stmt.targets) != 1 or not isinstance(assign_stmt.targets[0], ast.Name):
            return None

        dict_name = assign_stmt.targets[0].id

        if not isinstance(assign_stmt.value, ast.Dict):
            return None

        if assign_stmt.value.keys or assign_stmt.value.values:
            return None

        if not isinstance(for_stmt, ast.For):
            return None

        if len(for_stmt.body) != 1:
            return None

        only_stmt = for_stmt.body[0]
        condition = None
        mapping_assign = None

        if isinstance(only_stmt, ast.If):
            if only_stmt.orelse or len(only_stmt.body) != 1:
                return None

            condition = only_stmt.test
            mapping_assign = only_stmt.body[0]
        else:
            mapping_assign = only_stmt

        if not isinstance(mapping_assign, ast.Assign):
            return None

        if len(mapping_assign.targets) != 1:
            return None

        target = mapping_assign.targets[0]

        if not (
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Name)
            and target.value.id == dict_name
        ):
            return None

        dict_comp = ast.DictComp(
            key=target.slice,
            value=mapping_assign.value,
            generators=[
                ast.comprehension(
                    target=for_stmt.target,
                    iter=for_stmt.iter,
                    ifs=[condition] if condition is not None else [],
                    is_async=0,
                )
            ],
        )

        return ast.fix_missing_locations(
            ast.Assign(
                targets=[ast.Name(id=dict_name, ctx=ast.Store())],
                value=dict_comp,
            )
        )


def normalize_code(code: str) -> str:
    try:
        return ast.unparse(ast.parse(code)).strip()
    except Exception:
        return code.strip()


def transform_mapping_style(code: str) -> str:
    try:
        tree = ast.parse(code)
        transformer = MappingStyleTransformer()
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