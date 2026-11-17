"""32차: real edits vs action links; no frontend changes, no arbitrary code exec."""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import audit_transform_batch32 as audit32
from app.services.style_apply_service import _apply_style_action, _get_transform_function
from app.services.style_tag_transform_map_service import CREATE_ACTION_BY_TAG, COMPARE_ONLY_TAGS
from app.services.execution_validation_service import _find_block_reason
from test_style_batch31_new_links import TAG_SPEC, _src


class Audit32RegistryTests(unittest.TestCase):
    def test_complete_registry(self):
        self.assertEqual(len(CREATE_ACTION_BY_TAG), 102)
        self.assertEqual(len(COMPARE_ONLY_TAGS), 0)

    def test_all_actions_really_dispatch(self):
        for tag, action in CREATE_ACTION_BY_TAG.items():
            with self.subTest(tag=tag):
                self.assertTrue(callable(_get_transform_function(action)))

    def test_percentage_does_not_misstate_zero(self):
        self.assertIsNone(audit32._percentage(0, 0))
        self.assertEqual(audit32._percentage(2, 3), 66.67)

    def test_runtime_is_opt_in(self):
        with self.assertRaises(ValueError):
            audit32.audit(runtime_limit=-1)
        with self.assertRaises(ValueError):
            audit32.audit(runtime_limit=31)
        with self.assertRaises(ValueError):
            audit32.audit(runtime_limit=True)

    def test_async_guard_remains_enabled(self):
        self.assertIsNotNone(_find_block_reason("import asyncio\nprint('ok')\n"))
        self.assertIsNotNone(_find_block_reason("async def f():\n    return 1\n"))
        self.assertIsNone(_find_block_reason("print('ok')\n"))

    def test_direct_trace_observes_a_genuine_edit(self):
        action = TAG_SPEC["기본 매개변수"][1]
        fun = _get_transform_function(action)
        passed, detail, trace = audit32.trace_representative_case(
            "test_style_batch31_new_links.DefaultParameterTriplets.test_basic", fun)
        self.assertTrue(passed, detail)
        self.assertGreater(trace.calls, 0)
        self.assertGreater(trace.changed, 0)
        self.assertEqual(trace.invalid, 0)
        self.assertIsNotNone(trace.sample)
        self.assertNotEqual(*trace.sample)

    def test_trace_does_not_confuse_other_action(self):
        fun = _get_transform_function(TAG_SPEC["긴 함수 구조"][1])
        passed, detail, trace = audit32.trace_representative_case(
            "test_style_batch31_new_links.DefaultParameterTriplets.test_basic", fun)
        self.assertTrue(passed, detail)
        self.assertEqual(trace.calls, 0)
        self.assertIsNone(trace.sample)


class Audit32ActionSafetyTests(unittest.TestCase):
    def _apply(self, transformer):
        with patch("app.services.style_apply_service._get_transform_function", return_value=transformer):
            return _apply_style_action(
                code="print(1)\n",
                action_item={"tag": "test", "action": "create_probe", "reason": "safety"},
                applied_rules=[], warnings=[])

    def test_missing_action_does_not_modify_code(self):
        source, state = self._apply(None)
        self.assertEqual(source, "print(1)\n")
        self.assertEqual(state["status"], "transformer_missing")

    def test_exception_does_not_modify_code(self):
        def bad(code):
            raise RuntimeError("cannot parse")
        source, state = self._apply(bad)
        self.assertEqual(source, "print(1)\n")
        self.assertEqual(state["status"], "transformer_error")

    def test_non_string_does_not_modify_code(self):
        source, state = self._apply(lambda code: None)
        self.assertEqual(source, "print(1)\n")
        self.assertEqual(state["status"], "empty_result")

    def test_invalid_python_does_not_modify_code(self):
        source, state = self._apply(lambda code: "def broken(:\n    pass\n")
        self.assertEqual(source, "print(1)\n")
        self.assertEqual(state["status"], "invalid_result")

    def test_no_safe_pattern_does_not_modify_code(self):
        source, state = self._apply(lambda code: code)
        self.assertEqual(source, "print(1)\n")
        self.assertEqual(state["status"], "no_safe_pattern")

    def test_valid_changed_code_sets_applied(self):
        source, state = self._apply(lambda code: "print(2)\n")
        self.assertEqual(source, "print(2)\n")
        self.assertEqual(state["status"], "applied")

    def test_bad_syntax_on_all_actions_never_becomes_valid_edit(self):
        malformed = "def broken(:\n    pass\n"
        for tag, action in CREATE_ACTION_BY_TAG.items():
            with self.subTest(tag=tag):
                code, result = _apply_style_action(
                    code=malformed,
                    action_item={"tag": tag, "action": action, "reason": "malformed"},
                    applied_rules=[], warnings=[])
                self.assertEqual(code, malformed)
                self.assertNotEqual(result["status"], "applied")


def _make_triplet_probe(tag, action):
    def test(self):
        old = _src(tag, "additional")
        transform = _get_transform_function(action)
        new = transform(old)
        self.assertIsInstance(new, str)
        self.assertNotEqual(old, new)
        ast.parse(new)
        self.assertEqual(audit32.check_apply_action(tag, action, old), "applied")
    return test


class Audit32SevenNewTagApplications(unittest.TestCase):
    """Each late-stage tag must pass through production action application."""


for _tag, (_, _action) in TAG_SPEC.items():
    _fn = _make_triplet_probe(_tag, _action)
    _fn.__name__ = "test_" + _action
    setattr(Audit32SevenNewTagApplications, _fn.__name__, _fn)
del _tag, _action, _fn


if __name__ == "__main__":
    unittest.main()
