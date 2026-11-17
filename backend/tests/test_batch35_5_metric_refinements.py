"""Batch35-5: measured dominance, seven closed-pattern gates, safe diagnostics.

Run: python -m unittest discover -s tests -p 'test_batch35_5_metric_refinements.py' -v
"""
import ast
import copy
import json
import unittest

from app.services.metric_service import calculate_metrics
from app.services.style_diff_service import compare_style_with_target_code
from app.services.style_transform_plan_service import build_transform_plan
from app.services.style_action_diagnostic_service import build_transform_diagnostics
from app.services.style_apply_service import apply_coding_style
from app.services.style_metric_refinement_service import (
    add_dominant_default_actions,
    refine_closed_pattern_actions,
)


def complete_metrics(source=""):
    return calculate_metrics(ast.parse(source))


def make_diff(saved, target, current=True, concepts=()):
    style = {
        "syntax_tags": [], "concept_tags": [],
        "metrics": complete_metrics(saved),
    }
    if current:
        style["metrics_version"] = 1
    diff = compare_style_with_target_code(style, target)
    diff["style_concept_names"] = set(concepts)
    return diff


def action_names(plan):
    return [x.get("action") for x in plan["actions"]]


def sample(tag, action):
    return {"tag": tag, "action": action, "reason": "prior selection"}


class Batch35_5DominantDefaultTests(unittest.TestCase):
    DIRECTIONS = (
        ("sorted_reverse_false_explicit_count", "sorted_reverse_false_implicit_count",
         "sorted_call_count", "create_safe_explicit_sorted_reverse"),
        ("sorted_reverse_false_implicit_count", "sorted_reverse_false_explicit_count",
         "sorted_call_count", "create_safe_implicit_sorted_reverse"),
        ("strip_none_explicit_count", "strip_none_implicit_count",
         "string_strip_call_count", "create_safe_explicit_strip_default"),
        ("strip_none_implicit_count", "strip_none_explicit_count",
         "string_strip_call_count", "create_safe_implicit_strip_default"),
    )

    def synthetic(self, prefer, opposite, family, ratio=(3, 1), target_preferred=0,
                  current=True):
        saved = complete_metrics()
        target = complete_metrics()
        saved[prefer], saved[opposite] = ratio
        saved[family] = sum(ratio)
        target[prefer] = target_preferred
        target[opposite] = 2
        target[family] = target_preferred + 2
        return {
            "style_metrics": saved,
            "style_metrics_info": {
                "status": "current_complete" if current else "legacy_complete",
                "stored_version": 1 if current else None,
                "automatic_transforms_allowed": True,
            },
            "target_analysis": {"metrics": target},
            "style_syntax_names": set(), "style_concept_names": set(),
            "target_syntax_names": set(), "target_concept_names": set(),
            "missing_syntax_tags": [], "missing_concept_tags": [],
        }

    def test_all_four_mixed_dominant_directions_are_selected(self):
        for prefer, opposite, family, action in self.DIRECTIONS:
            with self.subTest(action=action):
                diff = self.synthetic(prefer, opposite, family)
                self.assertIn(action, action_names(build_transform_plan(diff)))

    def test_two_to_one_is_not_decisive(self):
        for prefer, opposite, family, action in self.DIRECTIONS:
            with self.subTest(action=action):
                diff = self.synthetic(prefer, opposite, family, ratio=(2, 1))
                self.assertNotIn(action, action_names(build_transform_plan(diff)))

    def test_three_to_two_is_not_decisive(self):
        for prefer, opposite, family, action in self.DIRECTIONS:
            with self.subTest(action=action):
                diff = self.synthetic(prefer, opposite, family, ratio=(3, 2))
                self.assertNotIn(action, action_names(build_transform_plan(diff)))

    def test_target_already_has_preferred_form_no_change(self):
        for prefer, opposite, family, action in self.DIRECTIONS:
            with self.subTest(action=action):
                diff = self.synthetic(prefer, opposite, family, target_preferred=1)
                self.assertNotIn(action, action_names(build_transform_plan(diff)))

    def test_unknown_counter_never_becomes_zero(self):
        prefer, opposite, family, action = self.DIRECTIONS[0]
        diff = self.synthetic(prefer, opposite, family)
        del diff["target_analysis"]["metrics"][prefer]
        self.assertNotIn(action, action_names(build_transform_plan(diff)))

    def test_legacy_style_with_mixed_evidence_retains_old_behavior(self):
        for prefer, opposite, family, action in self.DIRECTIONS:
            with self.subTest(action=action):
                diff = self.synthetic(prefer, opposite, family, current=False)
                self.assertNotIn(action, action_names(build_transform_plan(diff)))

    def test_no_duplicate_or_source_mutation(self):
        prefer, opposite, family, action = self.DIRECTIONS[0]
        diff = self.synthetic(prefer, opposite, family)
        before = copy.deepcopy(diff)
        original = [sample("sorted 사용", action)]
        result = add_dominant_default_actions(diff, original)
        self.assertEqual(result, original)
        self.assertEqual(diff, before)
        self.assertIsNot(result, original)

    def test_count_evidence_json_serializable(self):
        prefer, opposite, family, action = self.DIRECTIONS[0]
        diff = self.synthetic(prefer, opposite, family)
        selected = build_transform_plan(diff)["actions"]
        found = next(a for a in selected if a.get("action") == action)
        self.assertIn("3:1", found["reason"])
        self.assertIsInstance(json.dumps(found, ensure_ascii=False), str)


class Batch35_5ClosedStructuralGateTests(unittest.TestCase):
    DEFAULT_STYLE = "def _f(x=3):\n    return x\nprint(_f())\n"
    DEFAULT_TARGET = "def _f(x):\n    return x\nprint(_f(3))\n"
    VARARGS_STYLE = "def _f(*args):\n    x, y = args\n    return x + y\nprint(_f(1, 2))\n"
    VARARGS_TARGET = "def _f(x, y):\n    return x + y\nprint(_f(1, 2))\n"
    KWARGS_STYLE = ("def _f(**kwargs):\n    x = kwargs['x']\n"
                    "    y = kwargs['y']\n    return x + y\nprint(_f(x=1, y=2))\n")
    KWARGS_TARGET = "def _f(x, y):\n    return x + y\nprint(_f(x=1, y=2))\n"
    ASYNC_STYLE = ("import asyncio\nasync def _f():\n    return 5\n"
                   "print(asyncio.run(_f()))\n")
    ASYNC_TARGET = "import asyncio\ndef _f():\n    return 5\nprint(_f())\n"
    AWAIT_STYLE = ("import asyncio\nasync def _f():\n"
                   "    return await asyncio.sleep(0, result=5)\n"
                   "print(asyncio.run(_f()))\n")
    AWAIT_TARGET = ("import asyncio\nasync def _f():\n    return 5\n"
                    "print(asyncio.run(_f()))\n")
    STRUCTURE_STYLE = ("import asyncio\nasync def _f():\n    return 5\n"
                       "async def _runner():\n    return await _f()\n"
                       "print(asyncio.run(_runner()))\n")
    LONG_STYLE = "def _f():\n" + "".join("    print(%d)\n" % n for n in range(12)) + "_f()\n"
    LONG_TARGET = ("def _f():\n    for x in [" + ", ".join(str(i) for i in range(12)) +
                   "]:\n        print(x)\n_f()\n")

    def test_positive_all_seven_closed_pattern_families(self):
        cases = (
            ("create_safe_closed_default_parameter", self.DEFAULT_STYLE, self.DEFAULT_TARGET, ()),
            ("create_safe_closed_varargs", self.VARARGS_STYLE, self.VARARGS_TARGET, ()),
            ("create_safe_closed_kwargs", self.KWARGS_STYLE, self.KWARGS_TARGET, ()),
            ("create_safe_closed_async_definition", self.ASYNC_STYLE, self.ASYNC_TARGET, ()),
            ("create_safe_closed_await", self.AWAIT_STYLE, self.AWAIT_TARGET, ()),
            ("create_safe_closed_async_structure", self.STRUCTURE_STYLE, self.AWAIT_TARGET,
             ("비동기 처리 구조",)),
            ("create_safe_closed_long_function", self.LONG_STYLE, self.LONG_TARGET,
             ("긴 함수 구조",)),
        )
        for action, saved, target, concepts in cases:
            with self.subTest(action=action):
                diff = make_diff(saved, target, concepts=concepts)
                plan = build_transform_plan(diff)
                self.assertIn(action, action_names(plan))
                self.assertFalse(any(x.get("action") == action
                                     for x in plan.get("omitted_actions", [])))

    def test_default_parameter_without_used_parameter_is_excluded_and_explained(self):
        target = "def _f(x):\n    return 3\nprint(_f(3))\n"
        diff = make_diff(self.DEFAULT_STYLE, target)
        plan = build_transform_plan(diff)
        name = "create_safe_closed_default_parameter"
        self.assertNotIn(name, action_names(plan))
        omission = next(x for x in plan["omitted_actions"] if x["action"] == name)
        self.assertEqual(omission["reason_code"], "target_metric_shape_mismatch")
        self.assertTrue(any(f["metric"] == "used_function_parameter_count"
                            for f in omission["failed_conditions"]))
        report = build_transform_diagnostics(plan, [])
        self.assertTrue(any(x.get("reason_code") == "target_metric_shape_mismatch"
                            for x in report["omitted_actions"]))

    def test_varargs_wrong_number_of_parameters_excluded(self):
        diff = make_diff(self.VARARGS_STYLE, self.DEFAULT_TARGET)
        plan = build_transform_plan(diff)
        name = "create_safe_closed_varargs"
        self.assertNotIn(name, action_names(plan))
        omitted = next(x for x in plan["omitted_actions"] if x["action"] == name)
        self.assertTrue(any(f["metric"] == "function_parameter_count"
                            for f in omitted["failed_conditions"]))

    def test_kwargs_without_keyword_calls_excluded(self):
        diff = make_diff(self.KWARGS_STYLE, self.VARARGS_TARGET)
        plan = build_transform_plan(diff)
        name = "create_safe_closed_kwargs"
        self.assertNotIn(name, action_names(plan))
        omitted = next(x for x in plan["omitted_actions"] if x["action"] == name)
        self.assertTrue(any(f["metric"] == "keyword_arg_count"
                            for f in omitted["failed_conditions"]))

    def test_async_definition_with_parameter_excluded(self):
        target = "import asyncio\ndef _f(x):\n    return 5\nprint(_f(1))\n"
        plan = build_transform_plan(make_diff(self.ASYNC_STYLE, target))
        name = "create_safe_closed_async_definition"
        self.assertNotIn(name, action_names(plan))
        self.assertTrue(any(x.get("action") == name for x in plan["omitted_actions"]))

    def test_long_function_without_print_excluded(self):
        target = ("def _f():\n    for x in [1, 2]:\n        x += 1\n_f()\n")
        plan = build_transform_plan(make_diff(self.LONG_STYLE, target,
                                             concepts=("긴 함수 구조",)))
        name = "create_safe_closed_long_function"
        self.assertNotIn(name, action_names(plan))
        self.assertTrue(any(x.get("action") == name for x in plan["omitted_actions"]))

    def test_legacy_unversioned_style_does_not_change_selection(self):
        target = "def _f(x):\n    return 3\nprint(_f(3))\n"
        plan = build_transform_plan(make_diff(self.DEFAULT_STYLE, target, current=False))
        self.assertIn("create_safe_closed_default_parameter", action_names(plan))

    def test_empty_missing_target_metric_is_not_assumed_zero(self):
        diff = make_diff(self.DEFAULT_STYLE, self.DEFAULT_TARGET)
        diff["target_analysis"]["metrics"].pop("function_parameter_count")
        planned = [sample("기본 매개변수", "create_safe_closed_default_parameter")]
        selected, omitted = refine_closed_pattern_actions(diff, planned)
        self.assertEqual(selected, [])
        failed = [x for x in omitted[0]["failed_conditions"]
                  if x["metric"] == "function_parameter_count"]
        self.assertEqual(failed[0]["actual"], None)

    def test_unrelated_actions_keep_order_and_original_unchanged(self):
        diff = make_diff(self.DEFAULT_STYLE, self.DEFAULT_TARGET)
        before = [sample("A", "custom_a"),
                  sample("기본 매개변수", "create_safe_closed_default_parameter"),
                  sample("B", "custom_b")]
        orig = copy.deepcopy(before)
        kept, omitted = refine_closed_pattern_actions(diff, before)
        self.assertEqual(kept, before)
        self.assertEqual(omitted, [])
        self.assertEqual(before, orig)

    def test_legacy_behavior_bypasses_closed_gates(self):
        diff = make_diff(self.DEFAULT_STYLE, self.DEFAULT_TARGET, current=False)
        actions = [sample("기본 매개변수", "create_safe_closed_default_parameter")]
        kept, omissions = refine_closed_pattern_actions(diff, actions)
        self.assertEqual(kept, actions)
        self.assertEqual(omissions, [])


class Batch35_5EndToEndTests(unittest.TestCase):
    def test_observed_mixed_style_can_change_safe_sorted_default(self):
        saved = ("a = sorted([3, 2], reverse=False)\n"
                 "b = sorted([2, 1], reverse=False)\n"
                 "c = sorted([7, 6], reverse=False)\n"
                 "d = sorted([1, 2])\n")
        original = "out = sorted([3, 1])\n"
        style = {"syntax_tags": [], "concept_tags": [],
                 "metrics": complete_metrics(saved), "metrics_version": 1}
        diff = compare_style_with_target_code(style, original)
        self.assertIn("create_safe_explicit_sorted_reverse",
                      action_names(build_transform_plan(diff)))
        result = apply_coding_style(original, style)
        self.assertEqual(len(result), 6)
        self.assertIn("reverse=False", result[0])
        self.assertIn("transform_diagnostics", result[4])
        self.assertEqual(result[4]["style_metrics_info"]["status"], "current_complete")

    def test_strong_style_without_target_pattern_produces_no_forced_rewrite(self):
        saved = ("a = sorted([3, 2], reverse=False)\n"
                 "b = sorted([2, 1], reverse=False)\n"
                 "c = sorted([7, 6], reverse=False)\n"
                 "d = sorted([1, 2])\n")
        original = "z = 9\n"
        style = {"syntax_tags": [], "concept_tags": [],
                 "metrics": complete_metrics(saved), "metrics_version": 1}
        output = apply_coding_style(original, style)
        self.assertEqual(output[0], original)


if __name__ == "__main__":
    unittest.main()
