import ast


class CollectionStyleTransformer(ast.NodeTransformer):
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

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.generic_visit(node)
        node.body = self._transform_body(node.body)
        return node

    def visit_Assign(self, node: ast.Assign):
        self.generic_visit(node)

        if self.goal == "append":
            expanded = self._expand_comprehension_assignment(node)
            if expanded is not None:
                self.changed = True
                return expanded

        return node

    def _transform_body(self, body: list[ast.stmt]) -> list[ast.stmt]:
        if self.goal != "comprehension":
            return body

        new_body = []
        i = 0

        while i < len(body):
            if i + 1 < len(body):
                transformed = self._try_append_loop_to_comprehension(body[i], body[i + 1])
                if transformed is not None:
                    new_body.append(transformed)
                    self.changed = True
                    i += 2
                    continue

            new_body.append(body[i])
            i += 1

        return new_body

    def _try_append_loop_to_comprehension(self, assign_stmt: ast.stmt, for_stmt: ast.stmt):
        if not isinstance(assign_stmt, ast.Assign):
            return None

        if len(assign_stmt.targets) != 1 or not isinstance(assign_stmt.targets[0], ast.Name):
            return None

        result_name = assign_stmt.targets[0].id

        if not isinstance(assign_stmt.value, ast.List) or assign_stmt.value.elts:
            return None

        if not isinstance(for_stmt, ast.For):
            return None

        append_value, condition = self._extract_append(for_stmt, result_name)

        if append_value is None:
            return None

        return ast.fix_missing_locations(
            ast.Assign(
                targets=[ast.Name(id=result_name, ctx=ast.Store())],
                value=ast.ListComp(
                    elt=append_value,
                    generators=[
                        ast.comprehension(
                            target=for_stmt.target,
                            iter=for_stmt.iter,
                            ifs=[condition] if condition is not None else [],
                            is_async=0,
                        )
                    ],
                ),
            )
        )

    def _extract_append(self, for_stmt: ast.For, result_name: str):
        if len(for_stmt.body) != 1:
            return None, None

        only_stmt = for_stmt.body[0]
        condition = None

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

    def _expand_comprehension_assignment(self, node: ast.Assign):
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            return None

        target_name = node.targets[0].id

        if isinstance(node.value, ast.ListComp):
            return self._expand_list_comp(target_name, node.value)

        return None

    def _expand_list_comp(self, target_name: str, comp: ast.ListComp):
        if len(comp.generators) != 1:
            return None

        generator = comp.generators[0]

        if generator.is_async:
            return None

        result_assign = ast.Assign(
            targets=[ast.Name(id=target_name, ctx=ast.Store())],
            value=ast.List(elts=[], ctx=ast.Load()),
        )

        append_call = ast.Expr(
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id=target_name, ctx=ast.Load()),
                    attr="append",
                    ctx=ast.Load(),
                ),
                args=[comp.elt],
                keywords=[],
            )
        )

        loop_body = [append_call]

        for condition in reversed(generator.ifs):
            loop_body = [
                ast.If(
                    test=condition,
                    body=loop_body,
                    orelse=[],
                )
            ]

        for_node = ast.For(
            target=generator.target,
            iter=generator.iter,
            body=loop_body,
            orelse=[],
            type_comment=None,
        )

        return [
            ast.fix_missing_locations(result_assign),
            ast.fix_missing_locations(for_node),
        ]


def normalize_code(code: str) -> str:
    try:
        return ast.unparse(ast.parse(code)).strip()
    except Exception:
        return code.strip()


def _transform_collection(code: str, goal: str) -> str:
    try:
        tree = ast.parse(code)
        transformer = CollectionStyleTransformer(goal=goal)
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


def transform_to_append_collection_style(code: str) -> str:
    return _transform_collection(code, goal="append")


def transform_to_comprehension_collection_style(code: str) -> str:
    return _transform_collection(code, goal="comprehension")