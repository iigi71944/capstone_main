"""Conservatively reconcile partially reverted top-level Python code regions.

This module attributes surviving AST changes to transformations; it neither
executes code nor proves runtime equivalence. Only stable, uniquely identifiable
top-level functions, classes and named assignments participate. If statements
are inserted, removed, reordered or an unidentifiable statement changes, no
new cancellation is inferred. Batch 14's whole-program ledger still applies.
"""
from __future__ import annotations

import ast


def _anchor(node: ast.stmt) -> tuple[str, str] | None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return (type(node).__name__, node.name)
    if (isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)):
        return ('Assign', node.targets[0].id)
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return ('AnnAssign', node.target.id)
    return None


def _stable_scope_signatures(snapshots: list[str]) -> list[list[str]] | None:
    """Return AST signatures indexed by stable *position* or fail closed."""
    try:
        modules = [ast.parse(source) for source in snapshots]
    except (SyntaxError, TypeError, ValueError, UnicodeError, MemoryError, RecursionError):
        return None
    if not modules:
        return None
    original = modules[0].body
    names = [_anchor(statement) for statement in original]
    if not any(name is not None for name in names):
        return None
    identified = [name for name in names if name is not None]
    if len(identified) != len(set(identified)):
        return None  # duplicate assignments/functions cannot be identified uniquely
    output = []
    for module in modules:
        if len(module.body) != len(original):
            return None
        if [_anchor(stmt) for stmt in module.body] != names:
            return None
        try:
            output.append([ast.dump(stmt, include_attributes=False)
                           for stmt in module.body])
        except (TypeError, ValueError, MemoryError, RecursionError):
            return None
    # Unnamed statements are permitted only if unchanged in every snapshot.
    for position, name in enumerate(names):
        if name is None and len({row[position] for row in output}) != 1:
            return None
    # Track only eligible scopes; all others are proven unchanged.
    positions = [i for i, name in enumerate(names) if name is not None]
    return [[row[i] for i in positions] for row in output]


def mark_partially_reverted_actions(snapshots: list[str], results: list[dict]) -> int:
    """Cancel actions whose changes were fully undone in every stable scope.

    `snapshots[i]` is input to action `results[i]`, and `snapshots[i+1]`
    is its output. A snapshot stack is kept independently per uniquely named
    top-level scope. Returning to any earlier signature cancels the intervening
    scope contributions, including the action performing that reversal.

    Each applied action is only cancelled when *none* of its scope changes
    survive. If an action changed an untrackable region, the method returns 0
    without affecting any status. An earlier whole-file cancellation remains.
    """
    if len(snapshots) != len(results) + 1:
        raise ValueError('Action results and source snapshots must align.')
    if len(results) < 2:
        return 0
    # Avoid multiplying parsing/dumping cost on unusually large requests.
    # Defer to Batch 14's whole-program ledger instead.
    if len(snapshots) > 64 or any(len(source) > 250_000 for source in snapshots):
        return 0
    signatures = _stable_scope_signatures(snapshots)
    if signatures is None:
        return 0
    number_of_scopes = len(signatures[0])
    # Each stack entry is (scope AST signature, creating action index).
    stacks: list[list[tuple[str, int | None]]] = [
        [(signatures[0][scope], None)] for scope in range(number_of_scopes)
    ]
    touched: set[int] = set()
    for step, result in enumerate(results):
        if not isinstance(result, dict):
            return 0
        changed_scopes = [scope for scope in range(number_of_scopes)
                          if signatures[step][scope] != signatures[step + 1][scope]]
        if not changed_scopes:
            continue
        touched.add(step)
        if result.get('status') not in ('applied', 'cancelled_net_zero'):
            return 0  # never silently credit a failed/unknown action
        for scope in changed_scopes:
            new_sig = signatures[step + 1][scope]
            stack = stacks[scope]
            match = next((index for index in range(len(stack) - 1, -1, -1)
                          if stack[index][0] == new_sig), None)
            if match is not None:
                del stack[match + 1:]
            else:
                stack.append((new_sig, step))

    survives = {step for stack in stacks for _, step in stack if step is not None}
    cancelled = 0
    for step, result in enumerate(results):
        if result['status'] == 'applied' and step in touched and step not in survives:
            result['status'] = 'cancelled_net_zero'
            cancelled += 1
    return cancelled
