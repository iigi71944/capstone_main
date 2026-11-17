
"""AST 기반 코딩 스타일 측정 서비스.

값이 몇 번 등장했는지와 실제 코드 구조를 구분합니다.
반복 방식, 함수 매개변수 활용, 인덱스 역할 등은 AST 관계를 확인합니다.
기존 metrics 키는 호환성을 위해 유지합니다.
"""

import ast

# 문법 태그 추출과 동일한 수신 객체 자료형 판별기를 사용합니다.
# 메서드 이름이 겹치는 list.pop() / dict.pop() 등의 분류를 통일합니다.
from app.services.style_fine_pattern_metric_service import calculate_fine_pattern_metrics
# CAPSTONE_BATCH29_METRICS_IMPORT_V1
from app.services.syntax_tag_service import (
    _ReceiverTypeVisitor,
    STRING_METHODS,
    LIST_METHODS,
    DICT_METHODS,
)


class NestingDepthVisitor(ast.NodeVisitor):
    """조건·반복·자원·예외 구문이 중첩된 최대 깊이."""

    def __init__(self):
        self.current_depth = 0
        self.max_depth = 0

    def _visit_block(self, node: ast.AST) -> None:
        self.current_depth += 1
        self.max_depth = max(self.max_depth, self.current_depth)
        self.generic_visit(node)
        self.current_depth -= 1

    def visit_If(self, node: ast.If) -> None:
        self._visit_block(node)

    def visit_For(self, node: ast.For) -> None:
        self._visit_block(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_block(node)

    def visit_While(self, node: ast.While) -> None:
        self._visit_block(node)

    def visit_Try(self, node: ast.Try) -> None:
        self._visit_block(node)

    def visit_TryStar(self, node: ast.AST) -> None:
        self._visit_block(node)

    def visit_With(self, node: ast.With) -> None:
        self._visit_block(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._visit_block(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # 중첩 함수 안의 제어 흐름은 바깥 함수의 흐름에 합산하지 않습니다.
        old_depth = self.current_depth
        self.current_depth = 0
        self.generic_visit(node)
        self.current_depth = old_depth

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        old_depth = self.current_depth
        self.current_depth = 0
        self.generic_visit(node)
        self.current_depth = old_depth

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        old_depth = self.current_depth
        self.current_depth = 0
        self.generic_visit(node)
        self.current_depth = old_depth


def _is_named_call(node: ast.AST, function: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == function
    )


def _is_range_loop(node: ast.AST) -> bool:
    return isinstance(node, (ast.For, ast.AsyncFor)) and _is_named_call(
        node.iter, "range"
    )


def _subscript_uses_index(node: ast.AST, index_name: str) -> bool:
    """부분 문자열이 아닌 실제 [index] 접근이 있는지 확인합니다."""
    return any(
        isinstance(child, ast.Subscript)
        and isinstance(child.slice, ast.Name)
        and child.slice.id == index_name
        for child in ast.walk(node)
    )


def _body_uses_index(statements: list[ast.stmt], index_name: str) -> bool:
    return any(_subscript_uses_index(stmt, index_name) for stmt in statements)


def is_index_based_loop(node: ast.For) -> bool:
    """range(len(data)) 또는 range 인덱스로 data[i]에 접근하는 for문."""
    if not isinstance(node, (ast.For, ast.AsyncFor)):
        return False
    if not isinstance(node.target, ast.Name) or not _is_range_loop(node):
        return False

    call = node.iter
    if (
        len(call.args) == 1
        and not call.keywords
        and _is_named_call(call.args[0], "len")
        and len(call.args[0].args) == 1
    ):
        return True

    return _body_uses_index(node.body, node.target.id)


def is_direct_loop(node: ast.For) -> bool:
    """range 인덱스 생성이 아닌 iterable을 직접 순회하는 for문."""
    if not isinstance(node, (ast.For, ast.AsyncFor)):
        return False
    return not _is_range_loop(node)


def _is_one_step_increment(stmt: ast.stmt, index_name: str) -> bool:
    if isinstance(stmt, ast.AugAssign):
        return (
            isinstance(stmt.target, ast.Name)
            and stmt.target.id == index_name
            and isinstance(stmt.op, ast.Add)
            and isinstance(stmt.value, ast.Constant)
            and type(stmt.value.value) is int
            and stmt.value.value == 1
        )

    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
        target = stmt.targets[0]
        expr = stmt.value
        return (
            isinstance(target, ast.Name)
            and target.id == index_name
            and isinstance(expr, ast.BinOp)
            and isinstance(expr.op, ast.Add)
            and isinstance(expr.left, ast.Name)
            and expr.left.id == index_name
            and isinstance(expr.right, ast.Constant)
            and type(expr.right.value) is int
            and expr.right.value == 1
        )

    return False


def _while_len_index_candidates(test: ast.AST) -> set[str]:
    """while i < len(data)와 같은 비교식에서 후보 인덱스를 추출합니다."""
    result: set[str] = set()
    for child in ast.walk(test):
        if not isinstance(child, ast.Compare):
            continue
        if len(child.ops) != 1 or not isinstance(child.ops[0], (ast.Lt, ast.LtE)):
            continue
        if len(child.comparators) != 1:
            continue
        right = child.comparators[0]
        if (
            isinstance(child.left, ast.Name)
            and _is_named_call(right, "len")
            and len(right.args) == 1
        ):
            result.add(child.left.id)
    return result


def is_index_based_while(node: ast.While) -> bool:
    """인덱스 증가 + 길이 비교 + 자료구조 인덱싱을 모두 만족하는 while문."""
    if not isinstance(node, ast.While):
        return False

    for index_name in _while_len_index_candidates(node.test):
        if not _body_uses_index(node.body, index_name):
            continue
        if any(_is_one_step_increment(stmt, index_name) for stmt in node.body):
            return True
    return False


def get_function_body_length(node: ast.AST) -> int:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return len(node.body)
    return 0


def has_type_hint(node: ast.AST) -> bool:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.returns is not None:
            return True
        args = node.args
        all_parameters = [
            *args.posonlyargs,
            *args.args,
            *args.kwonlyargs,
        ]
        if args.vararg is not None:
            all_parameters.append(args.vararg)
        if args.kwarg is not None:
            all_parameters.append(args.kwarg)
        return any(arg.annotation is not None for arg in all_parameters)

    return isinstance(node, ast.AnnAssign)


def _has_default_parameter(node: ast.AST) -> bool:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    return bool(node.args.defaults) or any(
        value is not None for value in node.args.kw_defaults
    )


class _UsedParameterVisitor(ast.NodeVisitor):
    """중첩된 함수·클래스와 분리하여 매개변수 읽기만 추적합니다."""

    def __init__(self, parameter_names: set[str]):
        self.parameter_names = parameter_names
        self.used: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id in self.parameter_names:
            self.used.add(node.id)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return


def _function_parameter_usage(node: ast.AST) -> tuple[int, int]:
    """선언된 매개변수 수, 본문에서 참조된 서로 다른 매개변수 수."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return (0, 0)

    args = node.args
    parameters = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    if args.vararg is not None:
        parameters.append(args.vararg)
    if args.kwarg is not None:
        parameters.append(args.kwarg)

    # 메서드의 관례적 수신자 self/cls만으로 '매개변수 활용'을 판단하지 않습니다.
    parameter_names = {arg.arg for arg in parameters} - {"self", "cls"}
    visitor = _UsedParameterVisitor(parameter_names)
    for stmt in node.body:
        visitor.visit(stmt)
    return (len(parameter_names), len(visitor.used))


def _assigned_target_names(target: ast.AST) -> set[str]:
    """for문의 반복 변수를 추출합니다(튜플 언패킹 포함)."""
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for element in target.elts:
            names.update(_assigned_target_names(element))
        return names
    return set()


def _is_self_accumulation(target: str, expression: ast.AST) -> bool:
    """total = total + value 또는 total = value + total 패턴입니다."""
    if not isinstance(expression, ast.BinOp):
        return False
    if not isinstance(expression.op, (ast.Add, ast.Mult)):
        return False
    return (
        isinstance(expression.left, ast.Name)
        and expression.left.id == target
    ) or (
        isinstance(expression.right, ast.Name)
        and expression.right.id == target
    )


class _AggregationPatternVisitor(ast.NodeVisitor):
    """반복문 내부의 실제 누적 대입 패턴을 보수적으로 식별합니다.

    단순 대입/호출 횟수 대신 다음의 AST 관계를 확인합니다.
    - for/while 본문 내부에서 발생하는 누적 대입인지
    - 대입 대상이 해당 반복문의 제어 변수인지
    - 대입 식이 +=, *= 또는 기존 값 +/* 새 값인지

    이 분석은 정적 휴리스틱입니다. 실행 시의 실제 자료형, 분기 조건,
    사용자 정의 연산자 동작까지 확정하는 것은 아닙니다.
    """

    def __init__(self):
        self.count = 0
        self._loop_controls: list[set[str]] = []

    def _is_eligible(self, target: ast.AST) -> bool:
        if not self._loop_controls or not isinstance(target, ast.Name):
            return False
        return not any(target.id in controls for controls in self._loop_controls)

    def _visit_loop_body(self, body: list[ast.stmt], controls: set[str]) -> None:
        self._loop_controls.append(controls)
        try:
            for statement in body:
                self.visit(statement)
        finally:
            self._loop_controls.pop()

    def visit_For(self, node: ast.For) -> None:
        self._visit_loop_body(node.body, _assigned_target_names(node.target))
        # else 블록은 매 순회마다 실행되지 않으므로 반복 내부로 세지 않습니다.
        for statement in node.orelse:
            self.visit(statement)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_loop_body(node.body, _assigned_target_names(node.target))
        for statement in node.orelse:
            self.visit(statement)

    def visit_While(self, node: ast.While) -> None:
        # while의 조건에 참여하는 변수의 증가는 반복 제어일 수 있습니다.
        controls = {
            child.id
            for child in ast.walk(node.test)
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
        }
        self._visit_loop_body(node.body, controls)
        for statement in node.orelse:
            self.visit(statement)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if (
            self._is_eligible(node.target)
            and isinstance(node.op, (ast.Add, ast.Mult))
        ):
            self.count += 1
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if len(node.targets) == 1 and self._is_eligible(node.targets[0]):
            target = node.targets[0]
            if _is_self_accumulation(target.id, node.value):
                self.count += 1
        self.generic_visit(node)

    def _visit_new_scope(self, body: list[ast.stmt]) -> None:
        previous = self._loop_controls
        self._loop_controls = []
        try:
            for statement in body:
                self.visit(statement)
        finally:
            self._loop_controls = previous

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_new_scope(node.body)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_new_scope(node.body)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_new_scope(node.body)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        # lambda는 바깥 반복문의 본문이 아닙니다.
        return


def _loaded_names(node: ast.AST) -> set[str]:
    return {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name)
        and isinstance(child.ctx, ast.Load)
    }


def _iter_branches(statements: list[ast.stmt]):
    for statement in statements:
        yield statement

        if isinstance(
            statement,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            continue

        if isinstance(statement, ast.If):
            yield from _iter_branches(statement.body)
            yield from _iter_branches(statement.orelse)

        elif isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
            yield from _iter_branches(statement.body)
            yield from _iter_branches(statement.orelse)

        elif isinstance(statement, (ast.With, ast.AsyncWith)):
            yield from _iter_branches(statement.body)

        elif isinstance(statement, (ast.Try, ast.TryStar)):
            yield from _iter_branches(statement.body)
            for handler in statement.handlers:
                yield from _iter_branches(handler.body)
            yield from _iter_branches(statement.orelse)
            yield from _iter_branches(statement.finalbody)


class _SelectionPatternVisitor(ast.NodeVisitor):
    """필터링과 검색·탐색 패턴을 식별합니다."""

    def __init__(self):
        self.filter_count = 0
        self.search_count = 0
        self._loop_targets: list[set[str]] = []

    def _visit_for(self, node):
        self.visit(node.iter)
        targets = _assigned_target_names(node.target)

        self._loop_targets.append(targets)
        try:
            for statement in node.body:
                self.visit(statement)
        finally:
            self._loop_targets.pop()

        for statement in node.orelse:
            self.visit(statement)

    def visit_For(self, node):
        self._visit_for(node)

    def visit_AsyncFor(self, node):
        self._visit_for(node)

    def visit_While(self, node):
        self.visit(node.test)

        if is_index_based_while(node):
            targets = _while_len_index_candidates(node.test)
        else:
            targets = set()

        self._loop_targets.append(targets)
        try:
            for statement in node.body:
                self.visit(statement)
        finally:
            self._loop_targets.pop()

        for statement in node.orelse:
            self.visit(statement)

    def _test_reads_current_item(self, test):
        if not self._loop_targets:
            return False

        return bool(
            _loaded_names(test) & self._loop_targets[-1]
        )

    def _has_conditional_append(self, statements):
        targets = (
            set().union(*self._loop_targets)
            if self._loop_targets
            else set()
        )

        for statement in _iter_branches(statements):
            if not isinstance(statement, ast.Expr):
                continue

            call = statement.value

            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "append"
                and len(call.args) == 1
                and bool(_loaded_names(call.args[0]) & targets)
            ):
                return True

        return False

    def _has_early_exit(self, statements):
        # Break belongs to its nearest enclosing loop.
        # Return exits the enclosing function.

        class CurrentLoopExitVisitor(ast.NodeVisitor):
            def __init__(self):
                self.found = False
                self.nested_loop_depth = 0

            def visit_Break(self, node):
                if self.nested_loop_depth == 0:
                    self.found = True

            def visit_Return(self, node):
                self.found = True

            def _visit_inner_loop(self, node):
                self.nested_loop_depth += 1
                try:
                    self.generic_visit(node)
                finally:
                    self.nested_loop_depth -= 1

            def visit_For(self, node):
                self._visit_inner_loop(node)

            def visit_AsyncFor(self, node):
                self._visit_inner_loop(node)

            def visit_While(self, node):
                self._visit_inner_loop(node)

            def visit_FunctionDef(self, node):
                return

            def visit_AsyncFunctionDef(self, node):
                return

            def visit_ClassDef(self, node):
                return

            def visit_Lambda(self, node):
                return

        visitor = CurrentLoopExitVisitor()

        for statement in statements:
            visitor.visit(statement)

        return visitor.found

    def visit_If(self, node):
        if self._test_reads_current_item(node.test):
            if self._has_conditional_append(node.body):
                self.filter_count += 1

            if self._has_early_exit(node.body):
                self.search_count += 1

        self.generic_visit(node)

    def _visit_comprehension(self, node):
        if any(gen.ifs for gen in node.generators):
            self.filter_count += 1

        self.generic_visit(node)

    def visit_ListComp(self, node):
        self._visit_comprehension(node)

    def visit_SetComp(self, node):
        self._visit_comprehension(node)

    def visit_DictComp(self, node):
        self._visit_comprehension(node)

    def visit_GeneratorExp(self, node):
        self._visit_comprehension(node)

    def visit_Call(self, node):
        if _is_named_call(node, "filter") and len(node.args) >= 2:
            self.filter_count += 1

        if _is_named_call(node, "any") and node.args:
            if isinstance(node.args[0], ast.GeneratorExp):
                self.search_count += 1

        if _is_named_call(node, "next") and node.args:
            if isinstance(node.args[0], ast.GeneratorExp):
                self.search_count += 1

        self.generic_visit(node)

    def _visit_new_scope(self, body):
        previous = self._loop_targets
        self._loop_targets = []

        try:
            for statement in body:
                self.visit(statement)
        finally:
            self._loop_targets = previous

    def visit_FunctionDef(self, node):
        self._visit_new_scope(node.body)

    def visit_AsyncFunctionDef(self, node):
        self._visit_new_scope(node.body)

    def visit_ClassDef(self, node):
        self._visit_new_scope(node.body)

    def visit_Lambda(self, node):
        return


def calculate_metrics(tree: ast.AST) -> dict:
    function_count = 0
    async_function_count = 0
    class_count = 0
    loop_count = 0
    if_count = 0
    return_count = 0
    comprehension_count = 0
    index_loop_count = 0
    direct_loop_count = 0
    append_call_count = 0
    import_count = 0
    assign_count = 0
    aug_assign_count = 0
    call_count = 0
    compare_count = 0
    bool_op_count = 0
    bin_op_count = 0
    break_count = 0
    continue_count = 0
    try_count = 0
    raise_count = 0
    assert_count = 0
    with_count = 0
    lambda_count = 0
    collection_literal_count = 0
    list_literal_count = 0
    dict_literal_count = 0
    tuple_literal_count = 0
    subscript_count = 0
    slicing_count = 0
    attribute_count = 0
    match_count = 0
    decorator_count = 0
    string_literal_count = 0
    number_literal_count = 0
    boolean_literal_count = 0
    none_count = 0
    membership_op_count = 0
    identity_compare_count = 0
    if_exp_count = 0
    positional_arg_count = 0
    keyword_arg_count = 0
    default_param_count = 0
    vararg_count = 0
    kwarg_count = 0
    type_hint_count = 0
    f_string_count = 0
    print_call_count = 0
    input_call_count = 0
    len_call_count = 0
    range_call_count = 0
    sum_call_count = 0
    sorted_call_count = 0
    sort_method_call_count = 0
    enumerate_call_count = 0
    zip_call_count = 0
    open_call_count = 0
    string_method_call_count = 0
    list_method_call_count = 0
    dict_method_call_count = 0
    global_count = 0
    await_count = 0
    max_function_body_length = 0
    short_function_count = 0

    # 새 구조 분석 지표. 기존의 호출 인자 카운트와 구분합니다.
    function_parameter_count = 0
    used_function_parameter_count = 0
    parameter_using_function_count = 0
    while_index_loop_count = 0

    receiver_visitor = _ReceiverTypeVisitor()
    receiver_visitor.visit(tree)
    receiver_types = receiver_visitor.call_receiver_types

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_count += 1
            if isinstance(node, ast.AsyncFunctionDef):
                async_function_count += 1
            decorator_count += len(node.decorator_list)
            body_length = get_function_body_length(node)
            max_function_body_length = max(max_function_body_length, body_length)
            if body_length <= 5:
                short_function_count += 1
            if has_type_hint(node):
                type_hint_count += 1
            if _has_default_parameter(node):
                default_param_count += 1
            if node.args.vararg is not None:
                vararg_count += 1
            if node.args.kwarg is not None:
                kwarg_count += 1
            declared, used = _function_parameter_usage(node)
            function_parameter_count += declared
            used_function_parameter_count += used
            if used > 0:
                parameter_using_function_count += 1

        if isinstance(node, ast.ClassDef):
            class_count += 1
            decorator_count += len(node.decorator_list)

        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            loop_count += 1

        if isinstance(node, (ast.For, ast.AsyncFor)):
            if is_index_based_loop(node):
                index_loop_count += 1
            elif is_direct_loop(node):
                direct_loop_count += 1

        if isinstance(node, ast.While) and is_index_based_while(node):
            index_loop_count += 1
            while_index_loop_count += 1

        if isinstance(node, ast.If):
            if_count += 1

        if isinstance(node, ast.Return):
            return_count += 1

        if isinstance(node, (ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp)):
            comprehension_count += 1

        if isinstance(node, (ast.Import, ast.ImportFrom)):
            import_count += 1

        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            assign_count += 1
            if isinstance(node, ast.AnnAssign):
                type_hint_count += 1

        if isinstance(node, ast.AugAssign):
            aug_assign_count += 1

        if isinstance(node, ast.Call):
            call_count += 1
            if isinstance(node.func, ast.Name):
                builtin_name = node.func.id
                if builtin_name == "print":
                    print_call_count += 1
                elif builtin_name == "input":
                    input_call_count += 1
                elif builtin_name == "len":
                    len_call_count += 1
                elif builtin_name == "range":
                    range_call_count += 1
                elif builtin_name == "sum":
                    sum_call_count += 1
                elif builtin_name == "sorted":
                    sorted_call_count += 1
                elif builtin_name == "enumerate":
                    enumerate_call_count += 1
                elif builtin_name == "zip":
                    zip_call_count += 1
                elif builtin_name == "open":
                    open_call_count += 1

            if isinstance(node.func, ast.Attribute):
                method_name = node.func.attr
                receiver_type = receiver_types.get(id(node))

                if receiver_type == "list" and method_name in LIST_METHODS:
                    list_method_call_count += 1

                    if method_name == "append":
                        append_call_count += 1

                    if method_name == "sort":
                        sort_method_call_count += 1

                if receiver_type == "dict" and method_name in DICT_METHODS:
                    dict_method_call_count += 1

                if receiver_type == "str" and method_name in STRING_METHODS:
                    string_method_call_count += 1

            # 호출 인자(예: print(a, b))는 함수 선언 매개변수와 별개입니다.
            positional_arg_count += len(node.args)
            keyword_arg_count += sum(
                1 for keyword in node.keywords if keyword.arg is not None
            )

        if isinstance(node, ast.Compare):
            compare_count += 1
            for operator in node.ops:
                if isinstance(operator, (ast.In, ast.NotIn)):
                    membership_op_count += 1
                if isinstance(operator, (ast.Is, ast.IsNot)):
                    identity_compare_count += 1

        if isinstance(node, ast.BoolOp):
            bool_op_count += 1

        if isinstance(node, ast.BinOp):
            bin_op_count += 1

        if isinstance(node, ast.IfExp):
            if_exp_count += 1

        if isinstance(node, ast.Break):
            break_count += 1

        if isinstance(node, ast.Continue):
            continue_count += 1

        if isinstance(node, (ast.Try, ast.TryStar)):
            try_count += 1

        if isinstance(node, ast.Raise):
            raise_count += 1

        if isinstance(node, ast.Assert):
            assert_count += 1

        if isinstance(node, (ast.With, ast.AsyncWith)):
            with_count += 1

        if isinstance(node, ast.Lambda):
            lambda_count += 1

        if isinstance(node, ast.List):
            collection_literal_count += 1
            list_literal_count += 1

        if isinstance(node, ast.Dict):
            collection_literal_count += 1
            dict_literal_count += 1

        if isinstance(node, ast.Tuple):
            collection_literal_count += 1
            tuple_literal_count += 1

        if isinstance(node, ast.Set):
            collection_literal_count += 1

        if isinstance(node, ast.Subscript):
            subscript_count += 1
            if isinstance(node.slice, ast.Slice):
                slicing_count += 1

        if isinstance(node, ast.Attribute):
            attribute_count += 1

        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                string_literal_count += 1
            elif isinstance(node.value, bool):
                boolean_literal_count += 1
            elif isinstance(node.value, (int, float, complex)):
                number_literal_count += 1
            elif node.value is None:
                none_count += 1

        if isinstance(node, ast.JoinedStr):
            f_string_count += 1

        if isinstance(node, ast.Global):
            global_count += 1

        if isinstance(node, ast.Await):
            await_count += 1

        if isinstance(node, ast.Match):
            match_count += 1

    depth_visitor = NestingDepthVisitor()
    depth_visitor.visit(tree)

    aggregation_visitor = _AggregationPatternVisitor()
    aggregation_visitor.visit(tree)

    selection_visitor = _SelectionPatternVisitor()
    selection_visitor.visit(tree)

    # CAPSTONE_BATCH29_FINE_METRICS_V1: append detail keys, preserve all old keys.
    return {
        **calculate_fine_pattern_metrics(tree, receiver_types),
        "function_count": function_count,
        "async_function_count": async_function_count,
        "class_count": class_count,
        "loop_count": loop_count,
        "if_count": if_count,
        "return_count": return_count,
        "comprehension_count": comprehension_count,
        "index_loop_count": index_loop_count,
        "direct_loop_count": direct_loop_count,
        "append_call_count": append_call_count,
        "import_count": import_count,
        "assign_count": assign_count,
        "aug_assign_count": aug_assign_count,
        "call_count": call_count,
        "compare_count": compare_count,
        "bool_op_count": bool_op_count,
        "bin_op_count": bin_op_count,
        "break_count": break_count,
        "continue_count": continue_count,
        "try_count": try_count,
        "raise_count": raise_count,
        "assert_count": assert_count,
        "with_count": with_count,
        "lambda_count": lambda_count,
        "collection_literal_count": collection_literal_count,
        "list_literal_count": list_literal_count,
        "dict_literal_count": dict_literal_count,
        "tuple_literal_count": tuple_literal_count,
        "subscript_count": subscript_count,
        "slicing_count": slicing_count,
        "attribute_count": attribute_count,
        "match_count": match_count,
        "decorator_count": decorator_count,
        "string_literal_count": string_literal_count,
        "number_literal_count": number_literal_count,
        "boolean_literal_count": boolean_literal_count,
        "none_count": none_count,
        "membership_op_count": membership_op_count,
        "identity_compare_count": identity_compare_count,
        "if_exp_count": if_exp_count,
        "positional_arg_count": positional_arg_count,
        "keyword_arg_count": keyword_arg_count,
        "default_param_count": default_param_count,
        "vararg_count": vararg_count,
        "kwarg_count": kwarg_count,
        "type_hint_count": type_hint_count,
        "f_string_count": f_string_count,
        "print_call_count": print_call_count,
        "input_call_count": input_call_count,
        "len_call_count": len_call_count,
        "range_call_count": range_call_count,
        "sum_call_count": sum_call_count,
        "sorted_call_count": sorted_call_count,
        "sort_method_call_count": sort_method_call_count,
        "enumerate_call_count": enumerate_call_count,
        "zip_call_count": zip_call_count,
        "open_call_count": open_call_count,
        "string_method_call_count": string_method_call_count,
        "list_method_call_count": list_method_call_count,
        "dict_method_call_count": dict_method_call_count,
        "global_count": global_count,
        "await_count": await_count,
        "max_function_body_length": max_function_body_length,
        "short_function_count": short_function_count,
        "max_nesting_depth": depth_visitor.max_depth,
        "function_parameter_count": function_parameter_count,
        "used_function_parameter_count": used_function_parameter_count,
        "parameter_using_function_count": parameter_using_function_count,
        "while_index_loop_count": while_index_loop_count,
        "aggregation_pattern_count": aggregation_visitor.count,
        "filter_pattern_count": selection_visitor.filter_count,
        "search_pattern_count": selection_visitor.search_count,
    }
