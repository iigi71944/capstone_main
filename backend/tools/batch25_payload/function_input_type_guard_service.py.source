"""Conservative static preflight for explicit function-test arguments and stdin.

This never executes the user's code. Python input() returns str; conversions such
as int(input()) and float(input()) are validated only when the input sequence can
be determined from simple, straight-line statements. Unknown types and dynamic
control flow are left to Python's existing runtime checks.
"""
from __future__ import annotations

import ast

_MAX_SOURCE_CHARS = 250_000
_TYPES = {"int": int, "float": float, "str": str, "bool": bool,
          "list": list, "tuple": tuple, "dict": dict}


def _type_spec(node: ast.AST | None, depth: int = 0):
    if node is None or depth > 6:
        return None
    if isinstance(node, ast.Name) and node.id in _TYPES:
        return (node.id,)
    if isinstance(node, ast.Constant) and node.value is None:
        return ("None",)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        a = _type_spec(node.left, depth + 1)
        b = _type_spec(node.right, depth + 1)
        return ("union", a, b) if a is not None and b is not None else None
    if isinstance(node, ast.Subscript):
        name = None
        if isinstance(node.value, ast.Name):
            name = node.value.id
        elif isinstance(node.value, ast.Attribute) and isinstance(node.value.value, ast.Name):
            if node.value.value.id == "typing":
                name = node.value.attr
        item = node.slice
        if name in ("Optional", "Union"):
            args = item.elts if isinstance(item, ast.Tuple) else [item]
            members = [_type_spec(arg, depth + 1) for arg in args]
            if any(spec is None for spec in members):
                return None
            if name == "Optional" and len(members) == 1:
                return ("union", members[0], ("None",))
            if name == "Union" and len(members) >= 2:
                return ("multi_union", *members)
        if name in ("list", "List", "tuple", "Tuple", "dict", "Dict"):
            normalized = name.lower()
            parts = item.elts if isinstance(item, ast.Tuple) else [item]
            if normalized == "list" and len(parts) == 1:
                sub = _type_spec(parts[0], depth + 1)
                return ("list", sub) if sub else None
            if normalized == "dict" and len(parts) == 2:
                a, b = (_type_spec(x, depth + 1) for x in parts)
                return ("dict", a, b) if a and b else None
            if normalized == "tuple":
                if len(parts) == 2 and isinstance(parts[1], ast.Constant) and parts[1].value is Ellipsis:
                    sub = _type_spec(parts[0], depth + 1)
                    return ("tuple_any", sub) if sub else None
                subs = [_type_spec(x, depth + 1) for x in parts]
                return ("tuple_fixed", *subs) if all(subs) else None
    return None


def _matches(value: object, spec, depth: int = 0) -> bool:
    if depth > 7:
        return False
    name = spec[0]
    if name == "None":
        return value is None
    if name == "union":
        return _matches(value, spec[1], depth + 1) or _matches(value, spec[2], depth + 1)
    if name == "multi_union":
        return any(_matches(value, part, depth + 1) for part in spec[1:])
    if name == "list":
        return (type(value) is list and (len(spec) == 1 or
                all(_matches(x, spec[1], depth + 1) for x in value)))
    if name == "dict":
        return (type(value) is dict and (len(spec) == 1 or all(
            _matches(k, spec[1], depth + 1) and _matches(v, spec[2], depth + 1)
            for k, v in value.items())))
    if name == "tuple_any":
        return type(value) is tuple and all(_matches(x, spec[1], depth + 1) for x in value)
    if name == "tuple_fixed":
        return type(value) is tuple and len(value) == len(spec) - 1 and all(
            _matches(v, t, depth + 1) for v, t in zip(value, spec[1:]))
    return type(value) is _TYPES[name]


def _spec_name(spec) -> str:
    name = spec[0]
    if name == "union":
        return _spec_name(spec[1]) + " | " + _spec_name(spec[2])
    if name == "multi_union":
        return " | ".join(_spec_name(s) for s in spec[1:])
    if name in ("list", "tuple_any"):
        if len(spec) == 1:
            return "list" if name == "list" else "tuple"
        return ("list" if name == "list" else "tuple") + "[" + _spec_name(spec[1]) + "]"
    if name == "dict":
        if len(spec) == 1:
            return "dict"
        return "dict[" + _spec_name(spec[1]) + ", " + _spec_name(spec[2]) + "]"
    if name == "tuple_fixed":
        return "tuple[" + ", ".join(_spec_name(s) for s in spec[1:]) + "]"
    return name


def _default_spec(node: ast.AST | None):
    if isinstance(node, ast.Constant) and node.value is not None:
        n = type(node.value).__name__
        if n in _TYPES:
            return (n,)
    if isinstance(node, ast.List):
        return ("list",)
    if isinstance(node, ast.Tuple):
        return ("tuple",)
    if isinstance(node, ast.Dict):
        return ("dict",)
    return None


def _matches_default(value, spec):
    return type(value) is _TYPES[spec[0]]


def _guard_function_arguments(function: ast.FunctionDef | ast.AsyncFunctionDef, case: dict) -> None:
    args = case.get("args", [])
    kwargs = case.get("kwargs", {})
    if not isinstance(args, list) or not isinstance(kwargs, dict):
        return  # handled by the existing request validator
    params = list(function.args.posonlyargs) + list(function.args.args)
    kwonly = list(function.args.kwonlyargs)
    defaults = [None] * (len(params) - len(function.args.defaults)) + list(function.args.defaults)
    definitions = {}
    for param, default in zip(params, defaults):
        definitions[param.arg] = (_type_spec(param.annotation), _default_spec(default))
    for param, default in zip(kwonly, function.args.kw_defaults):
        definitions[param.arg] = (_type_spec(param.annotation), _default_spec(default))
    vararg = _type_spec(function.args.vararg.annotation) if function.args.vararg else None
    kwarg = _type_spec(function.args.kwarg.annotation) if function.args.kwarg else None
    checked = set()
    def check(label, value, declared, fallback):
        if declared is not None and not _matches(value, declared):
            raise ValueError(f"함수 '{function.name}'의 '{label}' 입력 타입이 맞지 않습니다: "
                             f"필요한 타입 {_spec_name(declared)}, 전달된 타입 {type(value).__name__}.")
        if declared is None and fallback is not None and not _matches_default(value, fallback):
            raise ValueError(f"함수 '{function.name}'의 '{label}' 입력 타입이 맞지 않습니다: "
                             f"기본값의 타입 {fallback[0]}, 전달된 타입 {type(value).__name__}.")
    for i, value in enumerate(args):
        if i < len(params):
            name = params[i].arg
            declared, fallback = definitions[name]
            check(name, value, declared, fallback)
            checked.add(name)
        elif vararg is not None:
            check("*" + function.args.vararg.arg, value, vararg, None)
    for name, value in kwargs.items():
        if name in definitions and name not in checked:
            declared, fallback = definitions[name]
            check(name, value, declared, fallback)
        elif name not in definitions and kwarg is not None:
            check("**" + function.args.kwarg.arg + "." + name, value, kwarg, None)


def _is_input_call(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "input" and not node.keywords and len(node.args) <= 1)


def _input_kind(expr: ast.AST) -> str | None:
    if _is_input_call(expr):
        return "str"
    if (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name)
            and expr.func.id in ("int", "float", "str") and not expr.keywords
            and len(expr.args) == 1 and _is_input_call(expr.args[0])):
        return expr.func.id
    return None


def _reads_any_input(node: ast.AST) -> bool:
    return any(_is_input_call(sub) for sub in ast.walk(node))


def _inputs_in_expression(expr: ast.AST) -> list[str] | None:
    """Recognize a single input() per statement, even inside return/print/math."""
    calls = [node for node in ast.walk(expr) if isinstance(node, ast.Call)]
    input_calls = [node for node in calls if _is_input_call(node)]
    if not input_calls:
        return []
    if len(input_calls) != 1:
        return None
    target = input_calls[0]
    parents = {child: parent for parent in ast.walk(expr) for child in ast.iter_child_nodes(parent)}
    parent = parents.get(target)
    kind = 'str'
    conversion = None
    if (isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name)
            and parent.func.id in ('int', 'float', 'str')
            and parent.args == [target] and not parent.keywords):
        conversion = parent
        kind = parent.func.id
    for call in calls:
        if call is target or call is conversion:
            continue
        # Direct print() evaluates its arguments first; a dynamic call could
        # consume stdin before the recognized conversion.
        if (isinstance(call.func, ast.Name) and call.func.id == 'print'
                and not call.keywords):
            continue
        return None
    return [kind]


def _straight_line_input_kinds(statements: list[ast.stmt]) -> list[str] | None:
    kinds = []
    unknown_call_before_input = False
    for stmt in statements:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                             ast.Import, ast.ImportFrom, ast.Pass)):
            continue
        if isinstance(stmt, ast.Assign):
            expr = stmt.value
        elif isinstance(stmt, ast.AnnAssign):
            expr = stmt.value
        elif isinstance(stmt, (ast.Expr, ast.Return)):
            expr = stmt.value
        else:
            if _reads_any_input(stmt):
                return None
            if any(isinstance(x, ast.Call) for x in ast.walk(stmt)):
                unknown_call_before_input = True
            continue
        if expr is None:
            continue
        found = _inputs_in_expression(expr)
        if found is None:
            return None
        if found:
            if unknown_call_before_input:
                return None
            kinds.extend(found)
        elif any(isinstance(x, ast.Call) for x in ast.walk(expr)):
            # Only a constant-only print is statically unable to consume stdin.
            if not (isinstance(expr, ast.Call)
                    and isinstance(expr.func, ast.Name) and expr.func.id == 'print'
                    and not expr.keywords
                    and all(isinstance(arg, ast.Constant) for arg in expr.args)):
                unknown_call_before_input = True
    return kinds


def _has_shadowed_builtins(tree: ast.Module, function: ast.AST) -> bool:
    """Do not ascribe builtin input/conversion semantics to rebound names."""
    sensitive = {'input', 'int', 'float', 'str'}
    if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
        params = (function.args.posonlyargs + function.args.args +
                  function.args.kwonlyargs)
        if any(arg.arg in sensitive for arg in params):
            return True
        if ((function.args.vararg is not None and function.args.vararg.arg in sensitive)
                or (function.args.kwarg is not None and function.args.kwarg.arg in sensitive)):
            return True
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            if node.id in sensitive:
                return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in sensitive:
                return True
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                binding = alias.asname or alias.name.split('.')[0]
                if binding in sensitive or alias.name == '*':
                    return True
    return False


def _guard_stdin(tree: ast.Module, function, stdin: str | None) -> None:
    if stdin is None:
        return
    # A preflight is meaningful only when all detected input calls have
    # statically clear ordering. Otherwise defer to normal Python runtime.
    module_kinds = _straight_line_input_kinds(tree.body)
    function_kinds = _straight_line_input_kinds(function.body)
    if module_kinds is None or function_kinds is None:
        return
    kinds = module_kinds + function_kinds
    if not kinds:
        return
    lines = stdin.splitlines()
    if len(lines) < len(kinds):
        raise ValueError(f"함수 테스트의 stdin 줄 수가 부족합니다: "
                         f"입력 {len(kinds)}개가 필요한데 {len(lines)}개를 전달했습니다.")
    for i, (kind, value) in enumerate(zip(kinds, lines), start=1):
        try:
            if kind == "int":
                int(value)
            elif kind == "float":
                float(value)
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"함수 테스트 stdin의 {i}번째 값은 {kind}(input())에 맞아야 합니다. "
                             f"현재 입력은 {kind} 타입으로 변환할 수 없습니다.") from exc


def validate_function_test_case(code: str, case: dict, stdin: str | None = None) -> None:
    """Reject clear mismatches; unknown/dynamic type contracts are not invented."""
    if not isinstance(code, str) or len(code) > _MAX_SOURCE_CHARS:
        return
    if not isinstance(case, dict):
        return
    name = case.get("function")
    if not isinstance(name, str):
        return
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, TypeError, RecursionError):
        return  # syntax errors are handled by the existing analyzer
    functions = [node for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(functions) != 1:
        return
    function = functions[0]
    # A decorator may replace the callable signature; async functions are not
    # awaited by the existing synchronous function-result harness.
    if function.decorator_list or isinstance(function, ast.AsyncFunctionDef):
        return
    # Annotated builtins can be rebound; avoid inventing an incorrect type.
    if not _has_shadowed_builtins(tree, function):
        _guard_function_arguments(function, case)
    selected_stdin = case.get("stdin")
    if selected_stdin is None:
        selected_stdin = stdin
    if isinstance(selected_stdin, str) and not _has_shadowed_builtins(tree, function):
        _guard_stdin(tree, function, selected_stdin)
