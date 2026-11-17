"""33차: 태그의 공개 변환 액션과 대표 테스트 안전형 함수를 구분합니다.

No production module is patched. Each triplet test observes the *actual*
implementation invoked by the existing repository regression fixture.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import audit_transform_batch33 as batch33
from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_transform_map_service import CREATE_ACTION_BY_TAG

TRIPLETS = {
    '딕셔너리 컴프리헨션': ('test_safe_dict_comprehension_upgrade', 'CollapseTests',
                             'test_basic', 'test_filter', 'test_nested_filters'),
    '리스트 누적 방식 사용': ('test_safe_list_comprehension_upgrade', 'ExpandTests',
                           'test_basic', 'test_filter', 'test_two_filters'),
    '리스트 컴프리헨션': ('test_safe_list_comprehension_upgrade', 'CollapseTests',
                       'test_basic', 'test_filter', 'test_two_nested_filters'),
    '인덱스 기반 반복 사용': ('test_safe_index_iteration_upgrade', 'IndexTests',
                            'test_basic_list', 'test_break_continue', 'test_unpacking'),
    '인덱싱 중심 구조': ('test_safe_index_iteration_upgrade', 'IndexTests',
                       'test_basic_list', 'test_break_continue', 'test_unpacking'),
    '직접 반복 사용': ('test_safe_index_iteration_upgrade', 'DirectTests',
                     'test_basic_list', 'test_preserves_index_in_body_with_enumerate',
                     'test_nested_function'),
}


def _run_three_pattern(self: unittest.TestCase, tag: str, level: int) -> None:
    module, klass, *cases = TRIPLETS[tag]
    test_id = f'{module}.{klass}.{cases[level]}'
    fn = batch33.MISSED_FIXTURES[tag][0]
    passed, error, trace = batch33.prior.trace_representative_case(test_id, fn)
    self.assertTrue(passed, f'{test_id}: {error}')
    self.assertGreater(trace.calls, 0, f'{tag}: no real call to the tested safe function')
    self.assertGreater(trace.changed, 0, f'{tag}: no real source edit')
    self.assertEqual(trace.invalid, 0, f'{tag}: generated invalid Python')
    self.assertIsNotNone(trace.sample, f'{tag}: no bounded example was observed')


class Batch33CoverageTests(unittest.TestCase):
    def test_01_six_linked_tags_exist(self):
        self.assertEqual(len(TRIPLETS), 6)
        self.assertEqual(set(TRIPLETS), set(batch33.MISSED_FIXTURES))
        self.assertEqual(len(CREATE_ACTION_BY_TAG), 102)
        for tag in TRIPLETS:
            self.assertIn(tag, CREATE_ACTION_BY_TAG)

    def test_02_three_safe_dispatcher_aliases_are_wired(self):
        expected = {
            '딕셔너리 컴프리헨션': 'create_safe_dict_comprehension',
            '리스트 누적 방식 사용': 'create_safe_append_collection',
            '리스트 컴프리헨션': 'create_safe_comprehension_collection',
        }
        for tag, action in expected.items():
            with self.subTest(tag=tag):
                safe_fn, safe_action = batch33.MISSED_FIXTURES[tag]
                self.assertEqual(safe_action, action)
                self.assertIs(_get_transform_function(action), safe_fn)

    def test_03_public_and_alternative_function_identity_are_different(self):
        # This difference was the exact reason the 32nd profiler missed 18
        # calls; never present it as a real transformation failure.
        for tag, (safe_fn, _) in batch33.MISSED_FIXTURES.items():
            with self.subTest(tag=tag):
                public = _get_transform_function(CREATE_ACTION_BY_TAG[tag])
                self.assertTrue(callable(public))
                self.assertIsNot(public, safe_fn)


# 6 tags x 3 distinct existing positive regression examples = 18 tests.
for _tag, _spec in TRIPLETS.items():
    # Use fixed readable method names, one class per tag, avoiding collisions.
    _class_name = 'Positive_' + str(list(TRIPLETS).index(_tag) + 1)
    _new = type(_class_name, (unittest.TestCase,), {})
    for _level, _kind in enumerate(('basic', 'additional', 'complex')):
        def _case(self, tag=_tag, idx=_level):
            _run_three_pattern(self, tag, idx)
        _case.__name__ = 'test_' + _kind
        setattr(_new, 'test_' + _kind, _case)
    globals()[_class_name] = _new

del _tag, _spec, _class_name, _new, _level, _kind, _case


if __name__ == '__main__':
    unittest.main()
