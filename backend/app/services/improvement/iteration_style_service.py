import ast


class ReplaceIndexWithItem(ast.NodeTransformer):
    def __init__(self, index_name: str, iterable_name: str, item_name: str):
        self.index_name = index_name
        self.iterable_name = iterable_name
        self.item_name = item_name

    def visit_Subscript(self, node: ast.Subscript):
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == self.iterable_name
            and isinstance(node.slice, ast.Name)
            and node.slice.id == self.index_name
        ):
            return ast.Name(id=self.item_name, ctx=ast.Load())

        return self.generic_visit(node)


class ReplaceItemWithIndexAccess(ast.NodeTransformer):
    def __init__(self, item_name: str, iterable_name: str, index_name: str):
        self.item_name = item_name
        self.iterable_name = iterable_name
        self.index_name = index_name

    def visit_Name(self, node: ast.Name):
        if node.id == self.item_name and isinstance(node.ctx, ast.Load):
            return ast.Subscript(
                value=ast.Name(id=self.iterable_name, ctx=ast.Load()),
                slice=ast.Name(id=self.index_name, ctx=ast.Load()),
                ctx=ast.Load(),
            )

        return node


class IterationStyleTransformer(ast.NodeTransformer):
    def __init__(self, goal: str):
        self.goal = goal
        self.changed = False

    def visit_For(self, node: ast.For):
        self.generic_visit(node)

        if self.goal == "direct":
            result = self._to_direct_iteration(node)
            if result is not None:
                self.changed = True
                return ast.fix_missing_locations(result)

        if self.goal == "index":
            result = self._to_index_iteration(node)
            if result is not None:
                self.changed = True
                return ast.fix_missing_locations(result)

        if self.goal == "while":
            result = self._to_while_iteration(node)
            if result is not None:
                self.changed = True
                return result

        return node

    def _to_direct_iteration(self, node: ast.For):
        if not (
            isinstance(node.target, ast.Name)
            and isinstance(node.iter, ast.Call)
            and isinstance(node.iter.func, ast.Name)
            and node.iter.func.id == "range"
            and len(node.iter.args) == 1
            and isinstance(node.iter.args[0], ast.Call)
            and isinstance(node.iter.args[0].func, ast.Name)
            and node.iter.args[0].func.id == "len"
            and len(node.iter.args[0].args) == 1
            and isinstance(node.iter.args[0].args[0], ast.Name)
        ):
            return None

        if node.orelse:
            return None

        index_name = node.target.id
        iterable_name = node.iter.args[0].args[0].id
        item_name = "item"

        replacer = ReplaceIndexWithItem(
            index_name=index_name,
            iterable_name=iterable_name,
            item_name=item_name,
        )

        new_body = [replacer.visit(stmt) for stmt in node.body]

        return ast.For(
            target=ast.Name(id=item_name, ctx=ast.Store()),
            iter=ast.Name(id=iterable_name, ctx=ast.Load()),
            body=new_body,
            orelse=[],
            type_comment=None,
        )

    def _to_index_iteration(self, node: ast.For):
        if not (
            isinstance(node.target, ast.Name)
            and isinstance(node.iter, ast.Name)
        ):
            return None

        if node.orelse:
            return None

        item_name = node.target.id
        iterable_name = node.iter.id
        index_name = "index"

        replacer = ReplaceItemWithIndexAccess(
            item_name=item_name,
            iterable_name=iterable_name,
            index_name=index_name,
        )

        new_body = [replacer.visit(stmt) for stmt in node.body]

        return ast.For(
            target=ast.Name(id=index_name, ctx=ast.Store()),
            iter=ast.Call(
                func=ast.Name(id="range", ctx=ast.Load()),
                args=[
                    ast.Call(
                        func=ast.Name(id="len", ctx=ast.Load()),
                        args=[ast.Name(id=iterable_name, ctx=ast.Load())],
                        keywords=[],
                    )
                ],
                keywords=[],
            ),
            body=new_body,
            orelse=[],
            type_comment=None,
        )

    def _to_while_iteration(self, node: ast.For):
        """
        안전한 단순 for 반복을 while 반복으로 변환합니다.

        변환 전:
        for item in items:
            print(item)

        변환 후:
        index = 0
        while index < len(items):
            item = items[index]
            print(item)
            index += 1

        안전 조건:
        - for target이 단순 변수여야 합니다.
        - for iter가 단순 변수여야 합니다.
        - for-else가 없어야 합니다.
        """

        if not (
            isinstance(node.target, ast.Name)
            and isinstance(node.iter, ast.Name)
        ):
            return None

        if node.orelse:
            return None

        item_name = node.target.id
        iterable_name = node.iter.id
        index_name = self._make_safe_index_name(node)

        index_init = ast.Assign(
            targets=[ast.Name(id=index_name, ctx=ast.Store())],
            value=ast.Constant(value=0),
        )

        item_assign = ast.Assign(
            targets=[ast.Name(id=item_name, ctx=ast.Store())],
            value=ast.Subscript(
                value=ast.Name(id=iterable_name, ctx=ast.Load()),
                slice=ast.Name(id=index_name, ctx=ast.Load()),
                ctx=ast.Load(),
            ),
        )

        index_increment = ast.AugAssign(
            target=ast.Name(id=index_name, ctx=ast.Store()),
            op=ast.Add(),
            value=ast.Constant(value=1),
        )

        while_node = ast.While(
            test=ast.Compare(
                left=ast.Name(id=index_name, ctx=ast.Load()),
                ops=[ast.Lt()],
                comparators=[
                    ast.Call(
                        func=ast.Name(id="len", ctx=ast.Load()),
                        args=[ast.Name(id=iterable_name, ctx=ast.Load())],
                        keywords=[],
                    )
                ],
            ),
            body=[
                item_assign,
                *node.body,
                index_increment,
            ],
            orelse=[],
        )

        return [
            ast.fix_missing_locations(index_init),
            ast.fix_missing_locations(while_node),
        ]

    def _make_safe_index_name(self, node: ast.For) -> str:
        used_names = set()

        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                used_names.add(child.id)

        base_name = "index"

        if base_name not in used_names:
            return base_name

        count = 1

        while f"{base_name}_{count}" in used_names:
            count += 1

        return f"{base_name}_{count}"


def normalize_code(code: str) -> str:
    try:
        return ast.unparse(ast.parse(code)).strip()
    except Exception:
        return code.strip()


def _transform_iteration(code: str, goal: str) -> str:
    try:
        tree = ast.parse(code)
        transformer = IterationStyleTransformer(goal=goal)
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


def transform_to_direct_iteration_style(code: str) -> str:
    return _transform_iteration(code, goal="direct")


def transform_to_index_iteration_style(code: str) -> str:
    return _transform_iteration(code, goal="index")


def transform_to_while_iteration_style(code: str) -> str:
    return _transform_iteration(code, goal="while")