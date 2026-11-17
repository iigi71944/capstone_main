"""Batch 36-3: conservative *necessary-shape* screening before dispatch.

Only three transformer families are screened. This does not prove that a
candidate is safe or that a rewrite will occur. False positives remain the
responsibility of the existing transformer; do not reject an AST shape which
its existing transformer can edit. Screening is run against the *current*
code immediately before the action, preserving multi-action opportunities.
"""
from __future__ import annotations

import ast
from typing import Any

SCREENED_ACTIONS = frozenset({
    "create_safe_operator_call",
    "create_safe_direct_attribute",
    "create_safe_keyword_call",
})
_OPERATORS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod)
_PRIMITIVES = (int, float, bool, str, type(None))


def _direct_value(statement: ast.stmt):
    if (isinstance(statement, ast.Assign) and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)):
        return statement.value
    if isinstance(statement, ast.Expr):
        return statement.value
    return None


def _candidate_operator_call(tree: ast.Module) -> bool:
    imports = [stmt for stmt in tree.body if isinstance(stmt, ast.Import)
               and any(alias.name == "operator" and alias.asname is None
                       for alias in stmt.names)]
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign) or not isinstance(stmt.value, ast.BinOp):
            continue
        if not (len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name)):
            continue
        if isinstance(stmt.value.op, _OPERATORS) and any(imp.lineno < stmt.lineno for imp in imports):
            return True
    return False


def _candidate_direct_attribute(tree: ast.Module) -> bool:
    for stmt in tree.body:
        value = _direct_value(stmt)
        if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                and value.func.id == "getattr" and len(value.args) == 2
                and not value.keywords and isinstance(value.args[0], ast.Name)
                and isinstance(value.args[1], ast.Constant)
                and type(value.args[1].value) is str):
            return True
    return False


def _candidate_keyword_call(tree: ast.Module) -> bool:
    # The existing transformer supports a direct top-level call; Batch36-3
    # additionally supports a single constant-argument call inside print().
    functions: dict[str, list[tuple[int, int]]] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.FunctionDef):
            functions.setdefault(stmt.name, []).append((stmt.lineno, len(stmt.args.args)))
    if not functions:
        return False
    for stmt in tree.body:
        outer = _direct_value(stmt)
        if not isinstance(outer, ast.Call):
            continue
        nested = False
        call = outer
        if (isinstance(outer.func, ast.Name) and outer.func.id == 'print'
                and isinstance(stmt, ast.Expr) and len(outer.args) == 1
                and not outer.keywords and isinstance(outer.args[0], ast.Call)):
            nested = True
            call = outer.args[0]
        if not (isinstance(call.func, ast.Name) and not call.keywords
                and call.args and not any(isinstance(arg, ast.Starred) for arg in call.args)):
            continue
        defs = functions.get(call.func.id, [])
        if len(defs) != 1 or defs[0][0] >= stmt.lineno or defs[0][1] != len(call.args):
            continue
        if nested and (len(tree.body) != 2 or stmt is not tree.body[1]):
            continue
        if nested and not all(isinstance(a, ast.Constant) and type(a.value) in _PRIMITIVES
                              for a in call.args):
            continue
        return True
    return False


_CANDIDATES = {
    "create_safe_operator_call": (_candidate_operator_call,
                                   "모듈 수준의 operator import 이후 지원 산술 대입이 없습니다."),
    "create_safe_direct_attribute": (_candidate_direct_attribute,
                                     "모듈 수준에서 직접 변환할 getattr(obj, 'name') 호출이 없습니다."),
    "create_safe_keyword_call": (_candidate_keyword_call,
                                 "모듈 수준에서 단순 함수의 직접/출력 내부 위치 인자 호출을 찾지 못했습니다."),
}


def screen_action_candidate(action: str, code: str) -> dict[str, Any] | None:
    """Return a skip diagnostic if a *necessary* AST shape is absent.

    Return None for unknown actions, unparseable inputs, or a plausible shape,
    so existing transformations and validation remain the final authority.
    """
    if action not in SCREENED_ACTIONS or not isinstance(code, str):
        return None
    try:
        tree = ast.parse(code)
    except (SyntaxError, TypeError, ValueError, RecursionError, MemoryError):
        return None
    check, reason = _CANDIDATES[action]
    if check(tree):
        return None
    return {
        "reason_code": "missing_required_ast_shape",
        "reason": reason,
        "screened_action": action,
        "preflight_version": 1,
    }


__all__ = ["screen_action_candidate", "SCREENED_ACTIONS"]
