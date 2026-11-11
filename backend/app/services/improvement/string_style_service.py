
import ast
from string import Formatter


STRING_CHAINABLE_METHODS = {
    "strip",
    "lstrip",
    "rstrip",
    "lower",
    "upper",
    "title",
    "capitalize",
    "replace",
}


class StringStyleTransformer(ast.NodeTransformer):
    """
    문자열 처리 중심 구조 변환기.

    같은 변수에 연속으로 적용되는 문자열 메서드를 체인으로 정리합니다.
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
            chained_stmt, consumed = self._try_transform_string_chain(body, i)

            if chained_stmt is not None:
                new_body.append(chained_stmt)
                self.changed = True
                i += consumed
                continue

            new_body.append(body[i])
            i += 1

        return new_body

    def _try_transform_string_chain(self, body: list[ast.stmt], start_index: int):
        first_info = self._parse_string_method_assignment(body[start_index])

        if first_info is None:
            return None, 0

        target_name, current_expr = first_info
        consumed = 1
        current_index = start_index + 1

        while current_index < len(body):
            next_info = self._parse_string_method_assignment(body[current_index])

            if next_info is None:
                break

            next_target_name, next_call = next_info

            if next_target_name != target_name:
                break

            if not self._call_uses_variable(next_call, target_name):
                break

            current_expr = self._replace_receiver_with_expr(
                call_node=next_call,
                new_receiver=current_expr,
            )

            consumed += 1
            current_index += 1

        if consumed < 2:
            return None, 0

        new_assign = ast.Assign(
            targets=[ast.Name(id=target_name, ctx=ast.Store())],
            value=current_expr,
        )

        return ast.fix_missing_locations(new_assign), consumed

    def _parse_string_method_assignment(self, stmt: ast.stmt):
        if not isinstance(stmt, ast.Assign):
            return None

        if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
            return None

        target_name = stmt.targets[0].id

        if not isinstance(stmt.value, ast.Call):
            return None

        call = stmt.value

        if not isinstance(call.func, ast.Attribute):
            return None

        if call.func.attr not in STRING_CHAINABLE_METHODS:
            return None

        return target_name, call

    def _call_uses_variable(self, call_node: ast.Call, variable_name: str) -> bool:
        return (
            isinstance(call_node.func, ast.Attribute)
            and isinstance(call_node.func.value, ast.Name)
            and call_node.func.value.id == variable_name
        )

    def _replace_receiver_with_expr(
        self,
        call_node: ast.Call,
        new_receiver: ast.expr,
    ) -> ast.Call:
        if not isinstance(call_node.func, ast.Attribute):
            return call_node

        new_call = ast.Call(
            func=ast.Attribute(
                value=new_receiver,
                attr=call_node.func.attr,
                ctx=ast.Load(),
            ),
            args=call_node.args,
            keywords=call_node.keywords,
        )

        return ast.fix_missing_locations(new_call)


def normalize_code(code: str) -> str:
    try:
        return ast.unparse(ast.parse(code)).strip()
    except Exception:
        return code.strip()


def transform_string_style(code: str) -> str:
    """기존 문자열 메서드 체인 변환 진입점입니다."""
    try:
        tree = ast.parse(code)
        transformer = StringStyleTransformer()
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


def _escape_fstring_literal(text: str, quote: str) -> str:
    """f-string의 문자 부분만 이스케이프합니다. 표현식 부분은 건드리지 않습니다."""
    return (
        text.replace("\\", "\\\\")
        .replace("{", "{{")
        .replace("}", "}}")
        .replace(quote, "\\" + quote)
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _build_fstring_for_format_call(code: str, node: ast.Call) -> str | None:
    """단일 필드를 가진 리터럴 .format() 호출만 안전하게 변환합니다."""
    if not (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
        and isinstance(node.func.value, ast.Constant)
        and isinstance(node.func.value.value, str)
    ):
        return None

    try:
        pieces = list(Formatter().parse(node.func.value.value))
    except ValueError:
        return None

    fields = [
        (index, name, spec, conversion)
        for index, (_, name, spec, conversion) in enumerate(pieces)
        if name is not None
    ]

    if len(fields) != 1:
        return None

    field_index, field_name, format_spec, conversion = fields[0]

    if format_spec or conversion:
        return None

    if len(node.args) == 1 and not node.keywords and field_name in ("", "0"):
        expression = node.args[0]
        if isinstance(expression, ast.Starred):
            return None
    elif (
        not node.args
        and len(node.keywords) == 1
        and node.keywords[0].arg == field_name
    ):
        expression = node.keywords[0].value
    else:
        return None

    expression_code = ast.get_source_segment(code, expression)

    # Python 3.11 f-string 표현식에서 사용할 수 없는 형태는 건너뜁니다.
    if not expression_code or any(
        char in expression_code for char in ("\n", "\r", "#", "\\")
    ):
        return None

    prefix = "".join(piece[0] for piece in pieces[: field_index + 1])
    suffix = "".join(piece[0] for piece in pieces[field_index + 1 :])

    for quote in ('"', "'"):
        # Python 3.11에서는 바깥 f-string과 표현식의 인용부호 재사용을 피합니다.
        if quote in expression_code:
            continue

        candidate = (
            "f" + quote
            + _escape_fstring_literal(prefix, quote)
            + "{" + expression_code + "}"
            + _escape_fstring_literal(suffix, quote)
            + quote
        )

        try:
            parsed = ast.parse(candidate, mode="eval")
        except SyntaxError:
            continue

        if not isinstance(parsed.body, ast.JoinedStr):
            continue

        formatted_values = [
            value for value in parsed.body.values
            if isinstance(value, ast.FormattedValue)
        ]

        if len(formatted_values) != 1:
            continue

        formatted_value = formatted_values[0]
        if formatted_value.conversion != -1 or formatted_value.format_spec is not None:
            continue

        if ast.dump(formatted_value.value, include_attributes=False) != ast.dump(
            expression, include_attributes=False
        ):
            continue

        return candidate

    return None


def transform_to_fstring_style(code: str) -> str:
    """단일 .format() 치환을 f-string으로 바꿉니다.

    - 원본 주석과 주변 서식을 보존합니다.
    - 여러 필드, 서식 지정자, 추가 인자는 원본 그대로 유지합니다.
    - 변경 대상이 겹치면 가장 안쪽 호출부터 변환합니다.
    - 변환 후 Python 문법을 다시 검사합니다.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code

    byte_lines = code.splitlines(keepends=True)
    offsets = [0]
    for line in byte_lines:
        offsets.append(offsets[-1] + len(line.encode("utf-8")))

    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent

    edits: list[tuple[int, int, bytes]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        # 다른 f-string의 표현식 내부는 Python 3.11 구문 제약 때문에 제외합니다.
        ancestor = parents.get(id(node))
        inside_fstring = False
        while ancestor is not None:
            if isinstance(ancestor, ast.JoinedStr):
                inside_fstring = True
                break
            ancestor = parents.get(id(ancestor))
        if inside_fstring:
            continue

        replacement = _build_fstring_for_format_call(code, node)
        if replacement is None:
            continue
        if node.end_lineno is None or node.end_col_offset is None:
            continue

        start = offsets[node.lineno - 1] + node.col_offset
        end = offsets[node.end_lineno - 1] + node.end_col_offset
        edits.append((start, end, replacement.encode("utf-8")))

    if not edits:
        return code

    selected: list[tuple[int, int, bytes]] = []
    for edit in sorted(edits, key=lambda item: item[1] - item[0]):
        if not any(
            edit[0] < old[1] and old[0] < edit[1]
            for old in selected
        ):
            selected.append(edit)

    output = code.encode("utf-8")
    for start, end, replacement in sorted(selected, key=lambda item: item[0], reverse=True):
        output = output[:start] + replacement + output[end:]

    transformed = output.decode("utf-8")
    try:
        ast.parse(transformed)
    except SyntaxError:
        return code

    return transformed
