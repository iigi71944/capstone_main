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


def has_decorator(node: ast.AST) -> bool:
    return hasattr(node, "decorator_list") and len(getattr(node, "decorator_list", [])) > 0


def has_type_hint(node: ast.AST) -> bool:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.returns is not None:
            return True

        for arg in node.args.args:
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

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            counter["함수 정의"] += 1

            if has_decorator(node):
                counter["데코레이터 사용"] += 1

            if has_type_hint(node):
                counter["타입 힌트 사용"] += 1

            if len(node.args.defaults) > 0 or len(node.args.kw_defaults) > 0:
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

            if len(node.args.defaults) > 0 or len(node.args.kw_defaults) > 0:
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

        elif isinstance(node, ast.For):
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

                if method_name in STRING_METHODS:
                    counter["문자열 메서드 호출"] += 1

                if method_name in LIST_METHODS:
                    counter["리스트 메서드 호출"] += 1

                if method_name in DICT_METHODS:
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

        elif isinstance(node, ast.Try):
            counter["예외 처리"] += 1

        elif isinstance(node, ast.Raise):
            counter["raise문"] += 1

        elif isinstance(node, ast.Assert):
            counter["assert문"] += 1

        elif isinstance(node, ast.With):
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