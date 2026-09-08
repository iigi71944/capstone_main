import ast


class DataProcessingTransformer(ast.NodeTransformer):
    """
    데이터 처리 중심 변환기.

    목표:
    - 실행 결과가 달라질 위험이 낮은 단순 데이터 처리 패턴만 변환합니다.
    - 간결성 중심형에서 집계, 필터링, 변환, 정렬 구조를 짧게 통합합니다.

    지원:
    1. total = 0 + for item in items: total += item -> total = sum(items)
    2. count = 0 + for item in items: if condition: count += 1 -> count = sum(1 for item in items if condition)
    3. result = [] + for item in items: result.append(expr) -> result = [expr for item in items]
    4. result = [] + for item in items: if condition: result.append(expr) -> result = [expr for item in items if condition]
    5. result = {} + for item in items: result[key] = value -> dict comprehension
    6. result = set() + for item in items: result.add(value) -> set comprehension
    7. values.sort() -> values = sorted(values)
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
                transformers = [
                    self._try_transform_sum_pattern,
                    self._try_transform_count_pattern,
                    self._try_transform_list_append_pattern,
                    self._try_transform_dict_assignment_pattern,
                    self._try_transform_set_add_pattern,
                ]

                transformed_pair = None

                for transformer in transformers:
                    transformed_pair = transformer(body[i], body[i + 1])
                    if transformed_pair is not None:
                        break

                if transformed_pair is not None:
                    new_body.append(transformed_pair)
                    self.changed = True
                    i += 2
                    continue

            sorted_node = self._try_transform_sort_call(body[i])
            if sorted_node is not None:
                new_body.append(sorted_node)
                self.changed = True
                i += 1
                continue

            new_body.append(body[i])
            i += 1

        return new_body

    def _try_transform_sum_pattern(self, assign_stmt: ast.stmt, for_stmt: ast.stmt):
        if not self._is_zero_assignment(assign_stmt):
            return None

        target_name = assign_stmt.targets[0].id

        if not isinstance(for_stmt, ast.For) or len(for_stmt.body) != 1:
            return None

        aug_stmt = for_stmt.body[0]

        if not (
            isinstance(aug_stmt, ast.AugAssign)
            and isinstance(aug_stmt.op, ast.Add)
            and isinstance(aug_stmt.target, ast.Name)
            and aug_stmt.target.id == target_name
            and isinstance(for_stmt.target, ast.Name)
            and isinstance(aug_stmt.value, ast.Name)
            and aug_stmt.value.id == for_stmt.target.id
        ):
            return None

        return ast.fix_missing_locations(
            ast.Assign(
                targets=[ast.Name(id=target_name, ctx=ast.Store())],
                value=ast.Call(
                    func=ast.Name(id="sum", ctx=ast.Load()),
                    args=[for_stmt.iter],
                    keywords=[],
                ),
            )
        )

    def _try_transform_count_pattern(self, assign_stmt: ast.stmt, for_stmt: ast.stmt):
        if not self._is_zero_assignment(assign_stmt):
            return None

        count_name = assign_stmt.targets[0].id

        if not isinstance(for_stmt, ast.For) or len(for_stmt.body) != 1:
            return None

        if_stmt = for_stmt.body[0]

        if not isinstance(if_stmt, ast.If) or if_stmt.orelse:
            return None

        if len(if_stmt.body) != 1:
            return None

        aug_stmt = if_stmt.body[0]

        if not (
            isinstance(aug_stmt, ast.AugAssign)
            and isinstance(aug_stmt.op, ast.Add)
            and isinstance(aug_stmt.target, ast.Name)
            and aug_stmt.target.id == count_name
            and isinstance(aug_stmt.value, ast.Constant)
            and aug_stmt.value.value == 1
        ):
            return None

        generator = ast.GeneratorExp(
            elt=ast.Constant(value=1),
            generators=[
                ast.comprehension(
                    target=for_stmt.target,
                    iter=for_stmt.iter,
                    ifs=[if_stmt.test],
                    is_async=0,
                )
            ],
        )

        return ast.fix_missing_locations(
            ast.Assign(
                targets=[ast.Name(id=count_name, ctx=ast.Store())],
                value=ast.Call(
                    func=ast.Name(id="sum", ctx=ast.Load()),
                    args=[generator],
                    keywords=[],
                ),
            )
        )

    def _try_transform_list_append_pattern(self, assign_stmt: ast.stmt, for_stmt: ast.stmt):
        if not isinstance(assign_stmt, ast.Assign):
            return None

        if len(assign_stmt.targets) != 1 or not isinstance(assign_stmt.targets[0], ast.Name):
            return None

        result_name = assign_stmt.targets[0].id

        if not isinstance(assign_stmt.value, ast.List) or assign_stmt.value.elts:
            return None

        if not isinstance(for_stmt, ast.For):
            return None

        if not isinstance(for_stmt.target, ast.Name):
            return None

        append_value, condition = self._extract_append_from_for(for_stmt, result_name)

        if append_value is None:
            return None

        comprehension = ast.ListComp(
            elt=append_value,
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
                targets=[ast.Name(id=result_name, ctx=ast.Store())],
                value=comprehension,
            )
        )

    def _try_transform_dict_assignment_pattern(self, assign_stmt: ast.stmt, for_stmt: ast.stmt):
        if not isinstance(assign_stmt, ast.Assign):
            return None

        if len(assign_stmt.targets) != 1 or not isinstance(assign_stmt.targets[0], ast.Name):
            return None

        result_name = assign_stmt.targets[0].id

        if not isinstance(assign_stmt.value, ast.Dict):
            return None

        if assign_stmt.value.keys or assign_stmt.value.values:
            return None

        if not isinstance(for_stmt, ast.For) or len(for_stmt.body) != 1:
            return None

        only_stmt = for_stmt.body[0]
        condition = None
        assign_inside = None

        if isinstance(only_stmt, ast.If):
            if only_stmt.orelse or len(only_stmt.body) != 1:
                return None
            condition = only_stmt.test
            assign_inside = only_stmt.body[0]
        else:
            assign_inside = only_stmt

        if not isinstance(assign_inside, ast.Assign):
            return None

        if len(assign_inside.targets) != 1:
            return None

        subscript_target = assign_inside.targets[0]

        if not (
            isinstance(subscript_target, ast.Subscript)
            and isinstance(subscript_target.value, ast.Name)
            and subscript_target.value.id == result_name
        ):
            return None

        dict_comp = ast.DictComp(
            key=subscript_target.slice,
            value=assign_inside.value,
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
                targets=[ast.Name(id=result_name, ctx=ast.Store())],
                value=dict_comp,
            )
        )

    def _try_transform_set_add_pattern(self, assign_stmt: ast.stmt, for_stmt: ast.stmt):
        if not isinstance(assign_stmt, ast.Assign):
            return None

        if len(assign_stmt.targets) != 1 or not isinstance(assign_stmt.targets[0], ast.Name):
            return None

        result_name = assign_stmt.targets[0].id

        if not (
            isinstance(assign_stmt.value, ast.Call)
            and isinstance(assign_stmt.value.func, ast.Name)
            and assign_stmt.value.func.id == "set"
            and not assign_stmt.value.args
            and not assign_stmt.value.keywords
        ):
            return None

        if not isinstance(for_stmt, ast.For) or len(for_stmt.body) != 1:
            return None

        only_stmt = for_stmt.body[0]
        condition = None
        add_stmt = None

        if isinstance(only_stmt, ast.If):
            if only_stmt.orelse or len(only_stmt.body) != 1:
                return None
            condition = only_stmt.test
            add_stmt = only_stmt.body[0]
        else:
            add_stmt = only_stmt

        if not (
            isinstance(add_stmt, ast.Expr)
            and isinstance(add_stmt.value, ast.Call)
            and isinstance(add_stmt.value.func, ast.Attribute)
            and isinstance(add_stmt.value.func.value, ast.Name)
            and add_stmt.value.func.value.id == result_name
            and add_stmt.value.func.attr == "add"
            and len(add_stmt.value.args) == 1
        ):
            return None

        set_comp = ast.SetComp(
            elt=add_stmt.value.args[0],
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
                targets=[ast.Name(id=result_name, ctx=ast.Store())],
                value=set_comp,
            )
        )

    def _extract_append_from_for(self, for_stmt: ast.For, result_name: str):
        if len(for_stmt.body) != 1:
            return None, None

        only_stmt = for_stmt.body[0]
        condition = None
        append_stmt = None

        if isinstance(only_stmt, ast.If):
            if only_stmt.orelse or len(only_stmt.body) != 1:
                return None, None
            condition = only_stmt.test
            append_stmt = only_stmt.body[0]
        else:
            append_stmt = only_stmt

        if not (
            isinstance(append_stmt, ast.Expr)
            and isinstance(append_stmt.value, ast.Call)
            and isinstance(append_stmt.value.func, ast.Attribute)
            and isinstance(append_stmt.value.func.value, ast.Name)
            and append_stmt.value.func.value.id == result_name
            and append_stmt.value.func.attr == "append"
            and len(append_stmt.value.args) == 1
        ):
            return None, None

        return append_stmt.value.args[0], condition

    def _try_transform_sort_call(self, stmt: ast.stmt):
        if not isinstance(stmt, ast.Expr):
            return None

        if not isinstance(stmt.value, ast.Call):
            return None

        call = stmt.value

        if not (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.attr == "sort"
        ):
            return None

        list_name = call.func.value.id

        return ast.fix_missing_locations(
            ast.Assign(
                targets=[ast.Name(id=list_name, ctx=ast.Store())],
                value=ast.Call(
                    func=ast.Name(id="sorted", ctx=ast.Load()),
                    args=[ast.Name(id=list_name, ctx=ast.Load())],
                    keywords=[],
                ),
            )
        )

    def _is_zero_assignment(self, stmt: ast.stmt) -> bool:
        return (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and isinstance(stmt.value, ast.Constant)
            and stmt.value.value == 0
        )


def normalize_code(code: str) -> str:
    try:
        return ast.unparse(ast.parse(code)).strip()
    except Exception:
        return code.strip()


def transform_data_processing_style(code: str) -> str:
    try:
        tree = ast.parse(code)
        transformer = DataProcessingTransformer()
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