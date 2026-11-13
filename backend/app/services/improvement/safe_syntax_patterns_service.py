"""Small, guarded AST rewrites for lambda/def, match/if, and local type hints.

Only simple syntactic idioms are supported. This is not a general refactoring
engine: unsupported scopes, introspection, comments in edits and unsupported
control flow are intentionally left alone. Runtime checking is still required.
"""

from __future__ import annotations

import ast
import copy
import tokenize

from app.services.improvement.safe_dict_comprehension_service import (
    _has_dynamic_names, _comments, _statement_blocks, _prepare_edit,
)


_PRIMITIVES = {int: 'int', float: 'float', str: 'str', bool: 'bool'}


def _sensitive(tree: ast.AST) -> bool:
    if _has_dynamic_names(tree):
        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {
            '__annotations__', '__name__', '__qualname__', '__code__',
            '__defaults__', '__dict__', '__doc__', '__closure__',
        }:
            return True
        if isinstance(node, ast.Name) and node.id in {
            'inspect', 'repr', 'help', 'getattr', 'vars', 'dir', 'globals', 'locals',
        }:
            return True
    return False


def _simple_args(args: ast.arguments) -> bool:
    return (not args.posonlyargs and not args.kwonlyargs and not args.vararg
            and not args.kwarg and not args.defaults and not args.kw_defaults
            and all(arg.annotation is None for arg in args.args))


def _lambda_to_def(stmt: ast.stmt):
    if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and isinstance(stmt.value, ast.Lambda)
            and _simple_args(stmt.value.args)):
        return None
    if any(isinstance(n, (ast.Yield, ast.YieldFrom, ast.Await, ast.NamedExpr))
           for n in ast.walk(stmt.value.body)):
        return None
    return [ast.FunctionDef(name=stmt.targets[0].id, args=copy.deepcopy(stmt.value.args),
                            body=[ast.Return(value=copy.deepcopy(stmt.value.body))],
                            decorator_list=[], returns=None, type_comment=None)]


def _def_to_lambda(stmt: ast.stmt):
    if not (isinstance(stmt, ast.FunctionDef) and not stmt.decorator_list
            and stmt.returns is None and len(stmt.body) == 1
            and isinstance(stmt.body[0], ast.Return) and stmt.body[0].value is not None
            and _simple_args(stmt.args) and not getattr(stmt, "type_params", [])):
        return None
    body = stmt.body[0].value
    if any(isinstance(n, (ast.Yield, ast.YieldFrom, ast.Await, ast.NamedExpr))
           for n in ast.walk(body)):
        return None
    # Skip direct self-reference: lambda assignment itself has different timing.
    if any(isinstance(n, ast.Name) and n.id == stmt.name
           for n in ast.walk(body)):
        return None
    return [ast.Assign(targets=[ast.Name(stmt.name, ast.Store())],
                       value=ast.Lambda(args=copy.deepcopy(stmt.args),
                                        body=copy.deepcopy(body)))]


def _if_condition(node: ast.expr):
    if not (isinstance(node, ast.Compare) and len(node.ops) == 1
            and isinstance(node.ops[0], ast.Eq)
            and isinstance(node.left, ast.Name) and len(node.comparators) == 1
            and isinstance(node.comparators[0], ast.Constant)
            and type(node.comparators[0].value) in (int, str)):
        return None
    return node.left.id, node.comparators[0].value


def _if_to_match(stmt: ast.stmt):
    if not isinstance(stmt, ast.If):
        return None
    cases = []
    subject = None
    current = stmt
    seen = set()
    while isinstance(current, ast.If):
        condition = _if_condition(current.test)
        if condition is None:
            return None
        name, literal = condition
        if subject is not None and name != subject:
            return None
        subject = name
        if (type(literal), literal) in seen:
            return None
        seen.add((type(literal), literal))
        cases.append(ast.match_case(
            pattern=ast.MatchValue(value=ast.Constant(literal)), guard=None,
            body=copy.deepcopy(current.body),
        ))
        if len(current.orelse) == 1 and isinstance(current.orelse[0], ast.If):
            current = current.orelse[0]
        else:
            if current.orelse:
                cases.append(ast.match_case(pattern=ast.MatchAs(), guard=None,
                                            body=copy.deepcopy(current.orelse)))
            break
    if len(cases) < 2:
        return None
    return [ast.Match(subject=ast.Name(subject, ast.Load()), cases=cases)]


def _match_to_if(stmt: ast.stmt):
    if not (isinstance(stmt, ast.Match) and isinstance(stmt.subject, ast.Name)
            and len(stmt.cases) >= 1):
        return None
    branches = []
    default = []
    seen = set()
    for i, case in enumerate(stmt.cases):
        if case.guard is not None:
            return None
        p = case.pattern
        if isinstance(p, ast.MatchAs) and p.name is None and p.pattern is None:
            if i != len(stmt.cases)-1:
                return None
            default = copy.deepcopy(case.body)
            continue
        if not (isinstance(p, ast.MatchValue) and isinstance(p.value, ast.Constant)
                and type(p.value.value) in (int, str)):
            return None
        key = (type(p.value.value), p.value.value)
        if key in seen:
            return None
        seen.add(key)
        branches.append((p.value.value, copy.deepcopy(case.body)))
    if not branches:
        return None
    orelse = default
    for literal, body in reversed(branches):
        orelse = [ast.If(
            test=ast.Compare(left=copy.deepcopy(stmt.subject), ops=[ast.Eq()],
                             comparators=[ast.Constant(literal)]),
            body=body, orelse=orelse,
        )]
    return orelse


def _local_hint(stmt: ast.stmt):
    if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and isinstance(stmt.value, ast.Constant)):
        return None
    value = stmt.value.value
    type_name = _PRIMITIVES.get(type(value))
    if type_name is None:
        return None
    return [ast.AnnAssign(target=copy.deepcopy(stmt.targets[0]),
                          annotation=ast.Name(type_name, ast.Load()),
                          value=copy.deepcopy(stmt.value), simple=1)]


def _remove_local_hint(stmt: ast.stmt):
    if not (isinstance(stmt, ast.AnnAssign) and stmt.simple == 1
            and isinstance(stmt.target, ast.Name) and stmt.value is not None
            and isinstance(stmt.annotation, ast.Name)
            and stmt.annotation.id in set(_PRIMITIVES.values())):
        return None
    return [ast.Assign(targets=[copy.deepcopy(stmt.target)], value=copy.deepcopy(stmt.value))]


def _stable_subject_predecessor(block: list[ast.stmt], i: int, stmt: ast.stmt) -> bool:
    """Only turn equality chains into match/if when the compared object has
    a known builtin immutable type at this point. Arbitrary objects may
    redefine __eq__ and cause observable comparisons/side effects.
    """
    if i < 1:
        return False
    name = None
    if isinstance(stmt, ast.Match) and isinstance(stmt.subject, ast.Name):
        name = stmt.subject.id
    elif isinstance(stmt, ast.If):
        condition = _if_condition(stmt.test)
        if condition:
            name = condition[0]
    if not name:
        return False
    prior = block[i - 1]
    return (isinstance(prior, ast.Assign) and len(prior.targets) == 1
            and isinstance(prior.targets[0], ast.Name)
            and prior.targets[0].id == name
            and isinstance(prior.value, ast.Constant)
            and type(prior.value.value) in (int, str))


def _function_name_call_only(stmt: ast.stmt, tree: ast.AST,
                             parent: dict[int, ast.AST]) -> bool:
    if isinstance(stmt, ast.FunctionDef):
        name = stmt.name
    elif (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
          and isinstance(stmt.targets[0], ast.Name)):
        name = stmt.targets[0].id
    else:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load):
            ancestor = parent.get(id(node))
            if not (isinstance(ancestor, ast.Call) and ancestor.func is node):
                return False
    return True


def _inside_function(stmt: ast.stmt, parent: dict[int, ast.AST]) -> bool:
    node = parent.get(id(stmt))
    while node is not None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return True
        if isinstance(node, (ast.Module, ast.ClassDef)):
            return False
        node = parent.get(id(node))
    return False


_TRANSFORMS = {
    'lambda_to_def': _lambda_to_def,
    'def_to_lambda': _def_to_lambda,
    'if_to_match': _if_to_match,
    'match_to_if': _match_to_if,
    'local_add_hint': _local_hint,
    'local_remove_hint': _remove_local_hint,
}


def _rewrite(code: str, direction: str) -> str:
    try:
        tree = ast.parse(code)
        if direction not in _TRANSFORMS or _sensitive(tree):
            return code
        parent = {id(ch): node for node in ast.walk(tree) for ch in ast.iter_child_nodes(node)}
        commented = _comments(code)
        edits = []
        for block in _statement_blocks(tree):
            for i, stmt in enumerate(block):
                if direction in ('if_to_match', 'match_to_if') and not _stable_subject_predecessor(block, i, stmt):
                    continue
                if direction.startswith('local_') and not _inside_function(stmt, parent):
                    continue
                if direction in ('lambda_to_def', 'def_to_lambda') and not _function_name_call_only(stmt, tree, parent):
                    continue
                # Def-to-lambda never rewrites class suites; handled by blocks.
                replacement = _TRANSFORMS[direction](stmt)
                if replacement is None:
                    continue
                edit = _prepare_edit(code, stmt, stmt, replacement, commented)
                if edit and not any(edit.start < e.end and e.start < edit.end for e in edits):
                    edits.append(edit)
        if not edits:
            return code
        result = code.encode('utf-8')
        for edit in sorted(edits, key=lambda e: e.start, reverse=True):
            result = result[:edit.start] + edit.replacement + result[edit.end:]
        changed = result.decode('utf-8')
        ast.parse(changed)
        return changed
    except (SyntaxError, ValueError, TypeError, RecursionError, UnicodeError, tokenize.TokenError):
        return code


def transform_lambda_to_def(code: str) -> str:
    return _rewrite(code, 'lambda_to_def')


def transform_def_to_lambda(code: str) -> str:
    return _rewrite(code, 'def_to_lambda')


def transform_if_to_match(code: str) -> str:
    return _rewrite(code, 'if_to_match')


def transform_match_to_if(code: str) -> str:
    return _rewrite(code, 'match_to_if')


def transform_add_local_type_hints(code: str) -> str:
    return _rewrite(code, 'local_add_hint')


def transform_remove_local_type_hints(code: str) -> str:
    return _rewrite(code, 'local_remove_hint')
