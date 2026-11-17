"""Batch 31: nontrivial positive triplets for seven previously unlinked tags.

The limited closed-module fixtures prove behavior only for these patterns, not
for dynamic code, real-world coroutine scheduling, introspection or all Python.
"""
from __future__ import annotations

import ast
import subprocess
import sys
import unittest

from app.services.improvement.safe_batch31_service import TRANSFORMERS
from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_transform_map_service import (
    CREATE_ACTION_BY_TAG, COMPARE_ONLY_TAGS, get_create_action_for_tag,
)
from app.services.style_transform_plan_service import build_transform_plan
from app.services.metric_service import calculate_metrics

TAG_SPEC = {
    '기본 매개변수': ('DefaultParameterTriplets', 'create_safe_closed_default_parameter'),
    '가변 인자 사용': ('VarargsTriplets', 'create_safe_closed_varargs'),
    '키워드 가변 인자 사용': ('KwargsTriplets', 'create_safe_closed_kwargs'),
    '비동기 함수 정의': ('AsyncDefinitionTriplets', 'create_safe_closed_async_definition'),
    'await 사용': ('AwaitTriplets', 'create_safe_closed_await'),
    '비동기 처리 구조': ('AsyncStructureTriplets', 'create_safe_closed_async_structure'),
    '긴 함수 구조': ('LongFunctionTriplets', 'create_safe_closed_long_function'),
}


def _run(source):
    p = subprocess.run([sys.executable, '-I', '-c', source],
                       capture_output=True, text=True, timeout=6)
    return p.returncode, p.stdout, p.stderr


def _src(tag, kind):
    nums = [(5, 8), (13, 21), (3, 4)]
    a, b = nums[{'basic': 0, 'additional': 1, 'complex': 2}[kind]]
    if tag == '기본 매개변수':
        expr = {'basic': 'x', 'additional': 'x + 1', 'complex': 'x * 2'}[kind]
        return f'def _identity(x):\n    return {expr}\nprint(_identity({a}))\n'
    if tag == '가변 인자 사용':
        expr = {'basic': 'a + b', 'additional': 'a * b', 'complex': 'a * b + 1'}[kind]
        return f'def _add(a, b):\n    return {expr}\nprint(_add({a}, {b}))\n'
    if tag == '키워드 가변 인자 사용':
        expr = {'basic': 'a + b', 'additional': 'a - b', 'complex': 'a + b + 1'}[kind]
        return f'def _add(a, b):\n    return {expr}\nprint(_add(a={a}, b={b}))\n'
    if tag == '비동기 함수 정의':
        expr = {'basic': f'{a}', 'additional': f'{a} + 1', 'complex': f'{a} * 2'}[kind]
        return f'import asyncio\ndef _value():\n    return {expr}\nprint(_value())\n'
    if tag in {'await 사용', '비동기 처리 구조'}:
        expr = {'basic': f'{a}', 'additional': f'{a} + 1', 'complex': f'{a} * 2'}[kind]
        return f'import asyncio\nasync def _value():\n    return {expr}\nprint(asyncio.run(_value()))\n'
    if tag == '긴 함수 구조':
        if kind == 'basic':
            items = ', '.join(str(i) for i in range(1, 11))
        elif kind == 'additional':
            items = ', '.join(repr(s) for s in list('abcdefghij'))
        else:
            items = ', '.join(f'{i}.5' for i in range(1, 13))
        seq = f'[{items}]' if kind == 'additional' else f'({items})'
        return f'def _emit():\n    for item in {seq}:\n        print(item)\n_emit()\n'
    raise KeyError(tag)


def _check_triplet(test, tag, kind):
    klass, action = TAG_SPEC[tag]
    transform = TRANSFORMERS[action]
    inp = _src(tag, kind)
    if kind == 'additional':
        inp = inp.replace('\n', '\r\n')
    out = transform(inp)
    test.assertNotEqual(out, inp, f'{tag} {kind} did not perform a real edit')
    ast.parse(out)
    test.assertEqual(_run(inp), _run(out), f'{tag} {kind} changed observable script outcome')
    test.assertEqual(transform(out), out, f'{tag} {kind} should be idempotent')
    test.assertEqual(get_create_action_for_tag(tag), action)
    test.assertIs(_get_transform_function(action), transform)
    if kind == 'additional':
        test.assertIn('\r\n', out)
        test.assertNotIn('\n', out.replace('\r\n', ''))


for _tag, (_name, _action) in TAG_SPEC.items():
    _klass = type(_name, (unittest.TestCase,), {})
    for _level in ('basic', 'additional', 'complex'):
        def _one(self, tag=_tag, level=_level):
            _check_triplet(self, tag, level)
        _one.__name__ = f'test_{_level}'
        setattr(_klass, f'test_{_level}', _one)
    globals()[_name] = _klass
# Avoid unittest discovering the final dynamically defined class twice.
del _klass, _tag, _name, _action, _level, _one


class Batch31SafetyTests(unittest.TestCase):
    def test_registry_all_tags_present_and_dispatch(self):
        self.assertEqual(len(CREATE_ACTION_BY_TAG), 102)
        self.assertEqual(len(COMPARE_ONLY_TAGS), 0)
        for tag, (_, action) in TAG_SPEC.items():
            self.assertEqual(CREATE_ACTION_BY_TAG[tag], action)
            self.assertIs(_get_transform_function(action), TRANSFORMERS[action])

    def test_existing_95_registry_actions_remain(self):
        for tag in ('with문', '리스트 컴프리헨션', '정렬 중심 구조', '전역 변수 사용'):
            self.assertIn(tag, CREATE_ACTION_BY_TAG)
            self.assertNotIn(tag, TAG_SPEC)

    def test_introspectable_public_functions_remain_unchanged(self):
        for tag, (_, action) in TAG_SPEC.items():
            src = _src(tag, 'basic').replace('_value', 'value').replace('_identity', 'identity').replace('_add', 'add').replace('_emit', 'emit')
            self.assertEqual(TRANSFORMERS[action](src), src, tag)

    def test_redefined_builtin_names_are_refused(self):
        for tag, (_, action) in TAG_SPEC.items():
            src = _src(tag, 'basic') + 'print = lambda x: x\n'
            self.assertEqual(TRANSFORMERS[action](src), src, tag)

    def test_dynamic_exec_is_refused(self):
        for tag, (_, action) in TAG_SPEC.items():
            src = _src(tag, 'basic') + 'exec("pass")\n'
            self.assertEqual(TRANSFORMERS[action](src), src, tag)

    def test_decorated_function_is_refused(self):
        for tag, (_, action) in TAG_SPEC.items():
            src = _src(tag, 'basic').replace('def _', '@staticmethod\ndef _', 1)
            self.assertEqual(TRANSFORMERS[action](src), src, tag)

    def test_source_comments_preserved_by_refusal(self):
        for tag, (_, action) in TAG_SPEC.items():
            src = '# original comment\n' + _src(tag, 'basic')
            self.assertEqual(TRANSFORMERS[action](src), src, tag)

    def test_source_imports_refused_when_extra(self):
        for tag, (_, action) in TAG_SPEC.items():
            src = 'import os\n' + _src(tag, 'basic')
            self.assertEqual(TRANSFORMERS[action](src), src, tag)

    def test_invalid_python_is_unchanged(self):
        for action, fun in TRANSFORMERS.items():
            bad = 'def _f(:\n    pass\n'
            self.assertEqual(fun(bad), bad, action)

    def test_no_signature_edits_without_closed_call(self):
        for action in ('create_safe_closed_default_parameter', 'create_safe_closed_varargs', 'create_safe_closed_kwargs'):
            code = 'def _id(a, b):\n    return a + b\n'
            self.assertEqual(TRANSFORMERS[action](code), code)

    def test_async_requires_owned_import(self):
        for action in ('create_safe_closed_async_definition', 'create_safe_closed_await', 'create_safe_closed_async_structure'):
            src = 'from asyncio import run\nasync def _value():\n    return 5\nprint(run(_value()))\n'
            self.assertEqual(TRANSFORMERS[action](src), src)

    def test_long_requires_ten_literal_items(self):
        code = 'def _emit():\n    for item in (1, 2, 3):\n        print(item)\n_emit()\n'
        self.assertEqual(TRANSFORMERS['create_safe_closed_long_function'](code), code)

    def test_long_does_not_expand_dynamic_iterables(self):
        code = 'def _emit():\n    for item in range(10):\n        print(item)\n_emit()\n'
        self.assertEqual(TRANSFORMERS['create_safe_closed_long_function'](code), code)

    def test_args_named_kwargs_conflict_is_refused(self):
        code = 'def _add(kwargs, b):\n    return kwargs + b\nprint(_add(kwargs=5, b=8))\n'
        self.assertEqual(TRANSFORMERS['create_safe_closed_kwargs'](code), code)

    def test_plan_missing_metric_is_noop(self):
        diff = {'style_metrics': {}, 'target_analysis': {'metrics': {}},
                'missing_syntax_tags': [{'tag': tag} for tag in TAG_SPEC],
                'missing_concept_tags': [], 'style_syntax_names': set(TAG_SPEC),
                'style_concept_names': set(TAG_SPEC), 'target_syntax_names': set(),
                'target_concept_names': set()}
        result = build_transform_plan(diff)
        new = set(TRANSFORMERS)
        self.assertFalse(new & {r.get('action') for r in result['actions']})

    def test_plan_metric_gates_for_each_tag(self):
        for tag, (_, action) in TAG_SPEC.items():
            before = _src(tag, 'basic')
            after = TRANSFORMERS[action](before)
            saved = calculate_metrics(ast.parse(after))
            target = calculate_metrics(ast.parse(before))
            concepts = {tag} if tag in {'비동기 처리 구조', '긴 함수 구조'} else set()
            diff = {'style_metrics': saved, 'target_analysis': {'metrics': target},
                    'missing_syntax_tags': [], 'missing_concept_tags': [],
                    'style_concept_names': concepts, 'style_syntax_names': {tag},
                    'target_syntax_names': set(), 'target_concept_names': set()}
            result = build_transform_plan(diff)
            self.assertEqual(sum(r.get('action') == action for r in result['actions']), 1, tag)

    def test_metric_gate_keeps_async_await_and_structure_exclusive(self):
        tag = '비동기 처리 구조'
        src = _src(tag, 'basic')
        saved = calculate_metrics(ast.parse(TRANSFORMERS[TAG_SPEC[tag][1]](src)))
        target = calculate_metrics(ast.parse(src))
        diff = {'style_metrics': saved, 'target_analysis': {'metrics': target},
                'missing_syntax_tags': [], 'missing_concept_tags': [],
                'style_concept_names': {'비동기 처리 구조'},
                'style_syntax_names': {'await 사용'},
                'target_syntax_names': set(), 'target_concept_names': set()}
        actions = {item.get('action') for item in build_transform_plan(diff)['actions']}
        self.assertIn('create_safe_closed_async_structure', actions)
        self.assertNotIn('create_safe_closed_await', actions)


if __name__ == '__main__':
    unittest.main()
