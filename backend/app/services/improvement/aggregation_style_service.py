import ast


class AggregationStyleTransformer(ast.NodeTransformer):
    def __init__(self, goal: str):
        self.goal = goal
        self.changed = False

    def visit_Module(self, node: ast.Module):
        self.generic_visit(node)
        node.body = self._transform_body(node.body)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.generic_visit(node)
        node.body = self._transform_body(node.body)
        return node

    def _transform_body(self, body: list[ast.stmt]) -> list[ast.stmt]:
        new_body = []
        i = 0

        while i < len(body):
            if self.goal == "sum" and i + 1 < len(body):
                transformed = self._loop_sum_to_sum_call(body[i], body[i + 1])
                if transformed is not None:
                    new_body.append(transformed)
                    self.changed = True
                    i += 2
                    continue

            if self.goal == "loop":
                expanded = self._sum_call_to_loop(body[i])
                if expanded is not None:
                    new_body.extend(expanded)
                    self.changed = True
                    i += 1
                    continue

            new_body.append(body[i])
            i += 1

        return new_body

    def _loop_sum_to_sum_call(self, assign_stmt: ast.stmt, for_stmt: ast.stmt):
        if not (
            isinstance(assign_stmt, ast.Assign)
            and len(assign_stmt.targets) == 1
            and isinstance(assign_stmt.targets[0], ast.Name)
            and isinstance(assign_stmt.value, ast.Constant)
            and assign_stmt.value.value == 0
            and isinstance(for_stmt, ast.For)
            and len(for_stmt.body) == 1
        ):
            return None

        target_name = assign_stmt.targets[0].id
        aug_stmt = for_stmt.body[0]

        if not (
            isinstance(aug_stmt, ast.AugAssign)
            and isinstance(aug_stmt.op, ast.Add)
            and isinstance(aug_stmt.target, ast.Name)
            and aug_stmt.target.id == target_name
            and isinstance(aug_stmt.value, ast.Name)
            and isinstance(for_stmt.target, ast.Name)
            and aug_stmt.value.id == for_stmt.target.id
        ):
            return None

        return ast.Assign(
            targets=[ast.Name(id=target_name, ctx=ast.Store())],
            value=ast.Call(
                func=ast.Name(id="sum", ctx=ast.Load()),
                args=[for_stmt.iter],
                keywords=[],
            ),
        )

    def _sum_call_to_loop(self, stmt: ast.stmt):
        if not (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
            and stmt.value.func.id == "sum"
            and len(stmt.value.args) == 1
        ):
            return None

        target_name = stmt.targets[0].id
        item_name = "item"

        return [
            ast.Assign(
                targets=[ast.Name(id=target_name, ctx=ast.Store())],
                value=ast.Constant(value=0),
            ),
            ast.For(
                target=ast.Name(id=item_name, ctx=ast.Store()),
                iter=stmt.value.args[0],
                body=[
                    ast.AugAssign(
                        target=ast.Name(id=target_name, ctx=ast.Store()),
                        op=ast.Add(),
                        value=ast.Name(id=item_name, ctx=ast.Load()),
                    )
                ],
                orelse=[],
                type_comment=None,
            ),
        ]


def normalize_code(code: str) -> str:
    try:
        return ast.unparse(ast.parse(code)).strip()
    except Exception:
        return code.strip()


def _transform_aggregation(code: str, goal: str) -> str:
    try:
        tree = ast.parse(code)
        transformer = AggregationStyleTransformer(goal=goal)
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


def transform_to_sum_aggregation_style(code: str) -> str:
    return _transform_aggregation(code, goal="sum")


def transform_to_loop_aggregation_style(code: str) -> str:
    return _transform_aggregation(code, goal="loop")