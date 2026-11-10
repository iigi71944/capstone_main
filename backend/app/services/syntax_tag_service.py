import ast
from collections import Counter

from app.services.tag_rule_service import enrich_syntax_tag


STRING_METHODS = {
    "strip",
    "split",
    "join",
    "replace",
    "lower",
    "upper",
    "startswith",
    "endswith",
    "find",
    "format",
}

LIST_METHODS = {
    "append",
    "extend",
    "insert",
    "remove",
    "pop",
    "sort",
    "reverse",
    "clear",
    "index",
    "count",
}

DICT_METHODS = {
    "get",
    "keys",
    "values",
    "items",
    "update",
    "pop",
    "setdefault",
    "clear",
}


BUILTIN_FUNCTION_TAGS = {
    "print": "print 사용",
    "input": "input 사용",
    "len": "len 사용",
    "range": "range 사용",
    "sum": "sum 사용",
    "sorted": "sorted 사용",
    "enumerate": "enumerate 사용",
    "zip": "zip 사용",
    "open": "open 사용",
}


# AST 문법 태그의 메서드 분류는 이름뿐 아니라 수신 객체의 자료형을 확인합니다.
# 예: list.pop()과 dict.pop()을 서로 다른 태그로 정확히 분리합니다.
_KNOWN_TYPES = {"list", "dict", "str", "tuple", "set"}
_CONSTRUCTOR_TYPES = {
    "list": "list", "dict": "dict", "str": "str",
    "tuple": "tuple", "set": "set",
}


def _annotation_type(annotation: ast.AST | None) -> str | None:
    """명시된 자료형 중 확실하게 구별되는 기본 자료형만 판별합니다."""
    if isinstance(annotation, ast.Name):
        name = annotation.id.lower()
        return name if name in _KNOWN_TYPES else None

    if isinstance(annotation, ast.Attribute):
        name = annotation.attr.lower()
        return name if name in _KNOWN_TYPES else None

    if isinstance(annotation, ast.Subscript):
        return _annotation_type(annotation.value)

    return None


class _ReceiverTypeVisitor(ast.NodeVisitor):
    """실행 순서와 함수별 범위를 고려해 메서드 수신 객체 자료형을 추정합니다.

    확인할 수 없는 자료형은 추측하지 않습니다. 추정치가 불확실하면
    '리스트 메서드 호출'이나 '딕셔너리 메서드 호출'로 분류하지 않습니다.
    """

    def __init__(self) -> None:
        self.scopes: list[dict[str, str | None]] = [{}]
        self.call_receiver_types: dict[int, str | None] = {}

    def _is_bound(self, name: str) -> bool:
        return any(name in scope for scope in reversed(self.scopes))

    def _lookup(self, name: str) -> str | None:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def _expression_type(self, node: ast.AST | None) -> str | None:
        if isinstance(node, ast.Name):
            return self._lookup(node.id)
        if isinstance(node, (ast.List, ast.ListComp)):
            return "list"
        if isinstance(node, (ast.Dict, ast.DictComp)):
            return "dict"
        if isinstance(node, (ast.Set, ast.SetComp)):
            return "set"
        if isinstance(node, ast.Tuple):
            return "tuple"
        if isinstance(node, (ast.JoinedStr,)):
            return "str"
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return "str"
        if isinstance(node, ast.IfExp):
            body_type = self._expression_type(node.body)
            else_type = self._expression_type(node.orelse)
            return body_type if body_type == else_type else None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left_type = self._expression_type(node.left)
            right_type = self._expression_type(node.right)
            if left_type == right_type and left_type in {"list", "str", "tuple"}:
                return left_type
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in _CONSTRUCTOR_TYPES and not self._is_bound(node.func.id):
                    return _CONSTRUCTOR_TYPES[node.func.id]
                if node.func.id == "sorted":
                    return "list"
                if node.func.id == "input":
                    return "str"
            if isinstance(node.func, ast.Attribute):
                owner_type = self._expression_type(node.func.value)
                method = node.func.attr
                if method == "copy" and owner_type in {"list", "dict", "set"}:
                    return owner_type
                if method == "split" and owner_type == "str":
                    return "list"
                if owner_type == "str" and method in {
                    "strip", "lstrip", "rstrip", "lower", "upper",
                    "replace", "join", "format", "capitalize", "title",
                }:
                    return "str"
        return None

    def _bind(self, target: ast.AST, value_type: str | None) -> None:
        if isinstance(target, ast.Name):
            self.scopes[-1][target.id] = value_type
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                self._bind(item, None)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        for target in node.targets:
            self.visit(target)
        kind = self._expression_type(node.value)
        for target in node.targets:
            self._bind(target, kind)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
        self.visit(node.target)
        kind = _annotation_type(node.annotation)
        if kind is None and node.value is not None:
            kind = self._expression_type(node.value)
        self._bind(node.target, kind)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        self._bind(node.target, self._expression_type(node.value))

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)
        self._bind(node.target, None)
        for statement in [*node.body, *node.orelse]:
            self.visit(statement)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.visit_For(node)

    def visit_If(self, node: ast.If) -> None:
        # 분기별로 달라질 수 있는 자료형은 확정하지 않습니다.
        self.visit(node.test)
        before = self.scopes[-1].copy()

        for statement in node.body:
            self.visit(statement)
        after_body = self.scopes[-1].copy()

        self.scopes[-1] = before.copy()
        for statement in node.orelse:
            self.visit(statement)
        after_else = self.scopes[-1].copy()

        self.scopes[-1] = {
            name: after_body.get(name)
            if after_body.get(name) == after_else.get(name)
            else None
            for name in set(after_body) | set(after_else)
        }

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                self.visit(default)
        self.scopes[-1][node.name] = None
        self.scopes.append({})
        args = [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ]
        for arg in args:
            self.scopes[-1][arg.arg] = _annotation_type(arg.annotation)
        if node.args.vararg:
            self.scopes[-1][node.args.vararg.arg] = "tuple"
        if node.args.kwarg:
            self.scopes[-1][node.args.kwarg.arg] = "dict"
        for statement in node.body:
            self.visit(statement)
        self.scopes.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        self.scopes[-1][node.name] = None
        self.scopes.append({})
        for statement in node.body:
            self.visit(statement)
        self.scopes.pop()

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                self.visit(default)
        self.scopes.append({})
        for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
            self.scopes[-1][arg.arg] = _annotation_type(arg.annotation)
        self.visit(node.body)
        self.scopes.pop()

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            self.call_receiver_types[id(node)] = self._expression_type(node.func.value)
        self.generic_visit(node)


def _has_default_parameter(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return bool(node.args.defaults) or any(
        value is not None for value in node.args.kw_defaults
    )


def has_decorator(node: ast.AST) -> bool:
    return hasattr(node, "decorator_list") and len(getattr(node, "decorator_list", [])) > 0


def has_type_hint(node: ast.AST) -> bool:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.returns is not None:
            return True

        for arg in [*node.args.posonlyargs, *node.args.args]:
            if arg.annotation is not None:
                return True

        for arg in node.args.kwonlyargs:
            if arg.annotation is not None:
                return True

        if node.args.vararg and node.args.vararg.annotation is not None:
            return True

        if node.args.kwarg and node.args.kwarg.annotation is not None:
            return True

    if isinstance(node, ast.AnnAssign):
        return True

    return False


def is_slice_node(node: ast.Subscript) -> bool:
    return isinstance(node.slice, ast.Slice)


def extract_syntax_tags(tree: ast.AST) -> list[dict]:
    counter = Counter()

    receiver_visitor = _ReceiverTypeVisitor()
    receiver_visitor.visit(tree)
    receiver_types = receiver_visitor.call_receiver_types

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            counter["함수 정의"] += 1

            if has_decorator(node):
                counter["데코레이터 사용"] += 1

            if has_type_hint(node):
                counter["타입 힌트 사용"] += 1

            if _has_default_parameter(node):
                counter["기본 매개변수"] += 1

            if node.args.vararg is not None:
                counter["가변 인자 사용"] += 1

            if node.args.kwarg is not None:
                counter["키워드 가변 인자 사용"] += 1

        elif isinstance(node, ast.AsyncFunctionDef):
            counter["함수 정의"] += 1
            counter["비동기 함수 정의"] += 1

            if has_decorator(node):
                counter["데코레이터 사용"] += 1

            if has_type_hint(node):
                counter["타입 힌트 사용"] += 1

            if _has_default_parameter(node):
                counter["기본 매개변수"] += 1

            if node.args.vararg is not None:
                counter["가변 인자 사용"] += 1

            if node.args.kwarg is not None:
                counter["키워드 가변 인자 사용"] += 1

        elif isinstance(node, ast.ClassDef):
            counter["클래스 정의"] += 1

            if has_decorator(node):
                counter["데코레이터 사용"] += 1

        elif isinstance(node, ast.If):
            counter["if문"] += 1

        elif isinstance(node, (ast.For, ast.AsyncFor)):
            counter["for문"] += 1

        elif isinstance(node, ast.While):
            counter["while문"] += 1

        elif isinstance(node, ast.Return):
            counter["return문"] += 1

        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            counter["import문"] += 1

        elif isinstance(node, ast.Assign):
            counter["변수 할당"] += 1

        elif isinstance(node, ast.AnnAssign):
            counter["변수 할당"] += 1
            counter["타입 힌트 사용"] += 1

        elif isinstance(node, ast.AugAssign):
            counter["복합 할당"] += 1

        elif isinstance(node, ast.Call):
            counter["함수 호출"] += 1

            if isinstance(node.func, ast.Name):
                builtin_tag = BUILTIN_FUNCTION_TAGS.get(node.func.id)
                if builtin_tag:
                    counter[builtin_tag] += 1

            if isinstance(node.func, ast.Attribute):
                method_name = node.func.attr

                receiver_type = receiver_types.get(id(node))

                if receiver_type == "str" and method_name in STRING_METHODS:
                    counter["문자열 메서드 호출"] += 1

                if receiver_type == "list" and method_name in LIST_METHODS:
                    counter["리스트 메서드 호출"] += 1

                if receiver_type == "dict" and method_name in DICT_METHODS:
                    counter["딕셔너리 메서드 호출"] += 1

            for arg in node.args:
                if arg is not None:
                    counter["위치 인자 사용"] += 1

            for keyword in node.keywords:
                if keyword.arg is not None:
                    counter["키워드 인자 사용"] += 1

        elif isinstance(node, ast.Compare):
            counter["비교 연산"] += 1

            for operator in node.ops:
                if isinstance(operator, ast.In) or isinstance(operator, ast.NotIn):
                    counter["멤버십 연산"] += 1

                if isinstance(operator, ast.Is) or isinstance(operator, ast.IsNot):
                    counter["식별 비교"] += 1

        elif isinstance(node, ast.BoolOp):
            counter["논리 연산"] += 1

        elif isinstance(node, ast.BinOp):
            counter["산술 연산"] += 1

        elif isinstance(node, ast.IfExp):
            counter["삼항 조건식"] += 1

        elif isinstance(node, ast.Break):
            counter["break문"] += 1

        elif isinstance(node, ast.Continue):
            counter["continue문"] += 1

        elif isinstance(node, (ast.Try, ast.TryStar)):
            counter["예외 처리"] += 1

        elif isinstance(node, ast.Raise):
            counter["raise문"] += 1

        elif isinstance(node, ast.Assert):
            counter["assert문"] += 1

        elif isinstance(node, (ast.With, ast.AsyncWith)):
            counter["with문"] += 1

        elif isinstance(node, ast.Lambda):
            counter["lambda식"] += 1

        elif isinstance(node, ast.ListComp):
            counter["리스트 컴프리헨션"] += 1

        elif isinstance(node, ast.DictComp):
            counter["딕셔너리 컴프리헨션"] += 1

        elif isinstance(node, ast.SetComp):
            counter["세트 컴프리헨션"] += 1

        elif isinstance(node, ast.GeneratorExp):
            counter["제너레이터 표현식"] += 1

        elif isinstance(node, ast.List):
            counter["리스트 리터럴"] += 1

        elif isinstance(node, ast.Dict):
            counter["딕셔너리 리터럴"] += 1

        elif isinstance(node, ast.Tuple):
            counter["튜플 리터럴"] += 1

        elif isinstance(node, ast.Subscript):
            counter["인덱싱 사용"] += 1

            if is_slice_node(node):
                counter["슬라이싱 사용"] += 1

        elif isinstance(node, ast.Attribute):
            counter["속성 접근"] += 1

        elif isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                counter["문자열 리터럴"] += 1
            elif isinstance(node.value, bool):
                counter["불리언 리터럴"] += 1
            elif isinstance(node.value, (int, float, complex)):
                counter["숫자 리터럴"] += 1
            elif node.value is None:
                counter["None 사용"] += 1

        elif isinstance(node, ast.JoinedStr):
            counter["f-string 사용"] += 1

        elif isinstance(node, ast.Global):
            counter["전역 변수 사용"] += 1

        elif isinstance(node, ast.Await):
            counter["await 사용"] += 1

        elif hasattr(ast, "Match") and isinstance(node, ast.Match):
            counter["패턴 매칭"] += 1

    tag_items = [{"tag": tag, "count": count} for tag, count in counter.items()]
    return [enrich_syntax_tag(item) for item in tag_items]