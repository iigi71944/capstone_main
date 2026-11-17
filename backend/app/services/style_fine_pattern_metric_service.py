"""Batch29 AST evidence: detailed method and explicit-default preferences.

Counts are observations, not proofs of runtime types. Receiver categories reuse
syntax_tag_service's existing inference, and never replace its broad metrics.
"""
from __future__ import annotations

import ast

_KEYS = (
    'list_extend_call_count', 'list_pop_call_count',
    'string_strip_call_count', 'string_split_call_count',
    'string_replace_call_count',
    'sorted_reverse_false_explicit_count',
    'sorted_reverse_false_implicit_count',
    'strip_none_explicit_count', 'strip_none_implicit_count',
)


def calculate_fine_pattern_metrics(tree: ast.AST, receiver_types: dict | None = None) -> dict:
    """Count narrowly identified AST patterns for saving and style selection."""
    counts = dict.fromkeys(_KEYS, 0)
    if not isinstance(tree, ast.AST):
        return counts
    receivers = receiver_types if isinstance(receiver_types, dict) else {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == 'sorted':
            if len(node.args) == 1 and not node.keywords:
                counts['sorted_reverse_false_implicit_count'] += 1
            elif (len(node.args) == 1 and len(node.keywords) == 1
                  and node.keywords[0].arg == 'reverse'
                  and isinstance(node.keywords[0].value, ast.Constant)
                  and node.keywords[0].value.value is False):
                counts['sorted_reverse_false_explicit_count'] += 1
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        method = node.func.attr
        receiver = receivers.get(id(node))
        if receiver == 'list':
            if method == 'extend':
                counts['list_extend_call_count'] += 1
            elif method == 'pop':
                counts['list_pop_call_count'] += 1
        elif receiver == 'str':
            if method == 'strip':
                counts['string_strip_call_count'] += 1
                if not node.args and not node.keywords:
                    counts['strip_none_implicit_count'] += 1
                elif (len(node.args) == 1 and not node.keywords
                      and isinstance(node.args[0], ast.Constant)
                      and node.args[0].value is None):
                    counts['strip_none_explicit_count'] += 1
            elif method == 'split':
                counts['string_split_call_count'] += 1
            elif method == 'replace':
                counts['string_replace_call_count'] += 1
    return counts
