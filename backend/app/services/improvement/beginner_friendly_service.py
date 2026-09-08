import ast


class IndexUsageChecker(ast.NodeVisitor):
    def __init__(self, index_name: str, iterable_name: str):
        self.index_name = index_name
        self.iterable_name = iterable_name
        self.safe = True

    def visit_Name(self, node: ast.Name):
        if node.id == self.index_name and isinstance(node.ctx, ast.Load):
            self.safe = False

    def visit_Subscript(self, node: ast.Subscript):
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == self.iterable_name
            and isinstance(node.slice, ast.Name)
            and node.slice.id == self.index_name
        ):
            return

        self.generic_visit(node)


class ReplaceIndexAccess(ast.NodeTransformer):
    def __init__(self, index_name: str, iterable_name: str, new_var_name: str):
        self.index_name = index_name
        self.iterable_name = iterable_name
        self.new_var_name = new_var_name

    def visit_Subscript(self, node: ast.Subscript):
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == self.iterable_name
            and isinstance(node.slice, ast.Name)
            and node.slice.id == self.index_name
        ):
            return ast.Name(id=self.new_var_name, ctx=ast.Load())

        return self.generic_visit(node)


class BeginnerFriendlyTransformer(ast.NodeTransformer):
    """
    학습 친화형 변환기.

    목표:
    - 실행 결과가 달라질 가능성이 높은 변환은 하지 않습니다.
    - 상위 문법이나 어려운 문법을 더 이해하기 쉬운 명시적 구조로 변환합니다.
    - 초보자가 코드 흐름을 따라가기 쉽도록 풀어쓴 구조를 만듭니다.

    적용 가능한 안전 변환:
    1. 리스트 컴프리헨션 -> 빈 리스트 + for + append
    2. 딕셔너리 컴프리헨션 -> 빈 딕셔너리 + for + key 할당
    3. 세트 컴프리헨션 -> 빈 set + for + add
    4. 단순 삼항 조건식 할당 -> 일반 if/else 할당
    5. range(len(...)) 반복 -> 직접 반복
    6. 복합 할당 +=, -=, *=, /= -> 일반 할당문
    """

    def __init__(self):
        self.changed = False

    def visit_Assign(self, node: ast.Assign):
        self.generic_visit(node)

        list_comp_nodes = self._expand_list_comprehension_assignment(node)
        if list_comp_nodes is not None:
            self.changed = True
            return list_comp_nodes

        dict_comp_nodes = self._expand_dict_comprehension_assignment(node)
        if dict_comp_nodes is not None:
            self.changed = True
            return dict_comp_nodes

        set_comp_nodes = self._expand_set_comprehension_assignment(node)
        if set_comp_nodes is not None:
            self.changed = True
            return set_comp_nodes

        if_exp_node = self._expand_if_expression_assignment(node)
        if if_exp_node is not None:
            self.changed = True
            return if_exp_node

        return node

    def visit_AugAssign(self, node: ast.AugAssign):
        self.generic_visit(node)

        if not isinstance(node.target, ast.Name):
            return node

        new_assign = ast.Assign(
            targets=[ast.Name(id=node.target.id, ctx=ast.Store())],
            value=ast.BinOp(
                left=ast.Name(id=node.target.id, ctx=ast.Load()),
                op=node.op,
                right=node.value,
            ),
        )

        self.changed = True
        return ast.fix_missing_locations(new_assign)

    def visit_For(self, node: ast.For):
        self.generic_visit(node)

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
            return node

        index_name = node.target.id
        iterable_name = node.iter.args[0].args[0].id
        new_var_name = "item"

        checker = IndexUsageChecker(index_name, iterable_name)

        for stmt in node.body:
            checker.visit(stmt)

        if not checker.safe:
            return node

        replacer = ReplaceIndexAccess(
            index_name=index_name,
            iterable_name=iterable_name,
            new_var_name=new_var_name,
        )

        new_body = [replacer.visit(stmt) for stmt in node.body]

        new_for = ast.For(
            target=ast.Name(id=new_var_name, ctx=ast.Store()),
            iter=ast.Name(id=iterable_name, ctx=ast.Load()),
            body=new_body,
            orelse=node.orelse,
            type_comment=None,
        )

        self.changed = True
        return ast.fix_missing_locations(new_for)

    def _expand_list_comprehension_assignment(self, node: ast.Assign):
        if not isinstance(node.value, ast.ListComp):
            return None

        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            return None

        target_name = node.targets[0].id
        comp = node.value

        if len(comp.generators) != 1:
            return None

        generator = comp.generators[0]

        if generator.is_async or not isinstance(generator.target, ast.Name):
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

    def _expand_dict_comprehension_assignment(self, node: ast.Assign):
        if not isinstance(node.value, ast.DictComp):
            return None

        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            return None

        target_name = node.targets[0].id
        comp = node.value

        if len(comp.generators) != 1:
            return None

        generator = comp.generators[0]

        if generator.is_async or not isinstance(generator.target, ast.Name):
            return None

        result_assign = ast.Assign(
            targets=[ast.Name(id=target_name, ctx=ast.Store())],
            value=ast.Dict(keys=[], values=[]),
        )

        key_assign = ast.Assign(
            targets=[
                ast.Subscript(
                    value=ast.Name(id=target_name, ctx=ast.Load()),
                    slice=comp.key,
                    ctx=ast.Store(),
                )
            ],
            value=comp.value,
        )

        loop_body = [key_assign]

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

    def _expand_set_comprehension_assignment(self, node: ast.Assign):
        if not isinstance(node.value, ast.SetComp):
            return None

        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            return None

        target_name = node.targets[0].id
        comp = node.value

        if len(comp.generators) != 1:
            return None

        generator = comp.generators[0]

        if generator.is_async or not isinstance(generator.target, ast.Name):
            return None

        result_assign = ast.Assign(
            targets=[ast.Name(id=target_name, ctx=ast.Store())],
            value=ast.Call(
                func=ast.Name(id="set", ctx=ast.Load()),
                args=[],
                keywords=[],
            ),
        )

        add_call = ast.Expr(
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id=target_name, ctx=ast.Load()),
                    attr="add",
                    ctx=ast.Load(),
                ),
                args=[comp.elt],
                keywords=[],
            )
        )

        loop_body = [add_call]

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

    def _expand_if_expression_assignment(self, node: ast.Assign):
        if not isinstance(node.value, ast.IfExp):
            return None

        if len(node.targets) != 1:
            return None

        target = node.targets[0]

        if not isinstance(target, ast.Name):
            return None

        return ast.If(
            test=node.value.test,
            body=[
                ast.Assign(
                    targets=[ast.Name(id=target.id, ctx=ast.Store())],
                    value=node.value.body,
                )
            ],
            orelse=[
                ast.Assign(
                    targets=[ast.Name(id=target.id, ctx=ast.Store())],
                    value=node.value.orelse,
                )
            ],
        )


def normalize_code(code: str) -> str:
    try:
        return ast.unparse(ast.parse(code)).strip()
    except Exception:
        return code.strip()


def transform_to_beginner_friendly(code: str) -> str:
    try:
        tree = ast.parse(code)

        transformer = BeginnerFriendlyTransformer()
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