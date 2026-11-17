"""35-1/35-2: 81 metrics, stored evidence and conflict resolution regressions.

Production code remains unchanged.
"""
import ast
import json
import unittest

from app.services.metric_service import calculate_metrics
from app.services.style_diff_service import analyze_code_style, compare_style_with_target_code
from app.services.style_transform_plan_service import (
    _metric_count, _resolve_collection_actions, _resolve_dictionary_actions,
    _resolve_iteration_actions, _resolve_new_family_actions, build_transform_plan,
    _NEW_FAMILY_PAIRS,
)
from app.services.style_tag_action_policy_service import (
    TAG_ACTION_POLICIES, SHARED_TAG_FAMILIES, finalize_tag_action_policies,
)


def entry(tag, action):
    return {"tag": tag, "action": action, "reason": "regression"}


def action_names(items):
    return [item["action"] for item in items]


class MetricRegression35(unittest.TestCase):
    def test_all_81_keys_and_serialization_across_samples(self):
        samples = [
            "", "x = 1\n", "def f(xs):\n    return [x for x in xs if x]\n",
            "values = [1, 2]\nvalues.extend([3])\nvalues.pop()\n",
            "s = ' a '\ns.strip()\ns.strip(None)\n",
            "sorted([2, 1])\nsorted([2, 1], reverse=False)\n",
            "async def f():\n    return 1\n",
            "for x in [1, 2]:\n    print(x)\n",
        ]
        expected_keys = set(calculate_metrics(ast.parse("")))
        self.assertEqual(len(expected_keys), 81)
        for source in samples:
            with self.subTest(source=source):
                counts = calculate_metrics(ast.parse(source))
                self.assertEqual(set(counts), expected_keys)
                self.assertTrue(all(type(v) is int and v >= 0 for v in counts.values()))
                self.assertEqual(json.loads(json.dumps(counts)), counts)
                self.assertEqual(analyze_code_style(source)["metrics"], counts)

    def test_saved_81_metrics_survive_comparison_unchanged(self):
        source = "def f(xs):\n    return [x for x in xs if x > 0]\n"
        analysis = analyze_code_style(source)
        original = json.loads(json.dumps(analysis["metrics"]))
        style = {"syntax_tags": analysis["syntax_tags"],
                 "concept_tags": analysis["concept_tags"],
                 "metrics": dict(original)}
        comparison = compare_style_with_target_code(style, "value = 1\n")
        self.assertEqual(comparison["style_metrics"], original)
        self.assertEqual(len(comparison["target_analysis"]["metrics"]), 81)
        comparison["style_metrics"]["function_count"] = 999
        self.assertEqual(style["metrics"], original)

    def test_legacy_missing_metrics_and_invalid_values(self):
        for invalid in (None, [], "invalid", 4):
            with self.subTest(invalid=invalid):
                result = compare_style_with_target_code(
                    {"syntax_tags": [], "concept_tags": [], "metrics": invalid},
                    "x = 1\n")
                self.assertEqual(result["style_metrics"], {})
        for invalid in (None, True, "3", -3, 1.5):
            self.assertEqual(_metric_count({"x": invalid}, "x"), 0)
        self.assertEqual(_metric_count({}, "unknown"), 0)

    def test_nine_fine_metric_extraction_patterns(self):
        source = ("values = [1, 2]\nvalues.extend([3])\nvalues.pop()\n"
                  "s = 'a b'\ns.strip()\ns.strip(None)\ns.split()\n"
                  "s.replace('a', 'b')\nsorted(values)\n"
                  "sorted(values, reverse=False)\n")
        metrics = calculate_metrics(ast.parse(source))
        expected = {
            "list_extend_call_count": 1, "list_pop_call_count": 1,
            "string_strip_call_count": 2, "string_split_call_count": 1,
            "string_replace_call_count": 1,
            "sorted_reverse_false_explicit_count": 1,
            "sorted_reverse_false_implicit_count": 1,
            "strip_none_explicit_count": 1, "strip_none_implicit_count": 1,
        }
        for key, value in expected.items():
            with self.subTest(metric=key):
                self.assertEqual(metrics[key], value)

    def test_metric_evidence_required_for_sorted_conversion(self):
        def selected(saved, target):
            diff = {
                "style_metrics": saved, "target_analysis": {"metrics": target},
                "style_syntax_names": set(), "target_syntax_names": set(),
                "style_concept_names": set(), "target_concept_names": set(),
                "missing_syntax_tags": [], "missing_concept_tags": [],
            }
            return action_names(build_transform_plan(diff)["actions"])
        explicit = {"sorted_reverse_false_explicit_count": 1,
                    "sorted_reverse_false_implicit_count": 0, "sorted_call_count": 1}
        implicit = {"sorted_reverse_false_explicit_count": 0,
                    "sorted_reverse_false_implicit_count": 1, "sorted_call_count": 1}
        desired = "create_safe_explicit_sorted_reverse"
        self.assertIn(desired, selected(explicit, implicit))
        self.assertNotIn(desired, selected({}, implicit))
        self.assertNotIn(desired, selected(explicit, {}))
        self.assertNotIn(desired, selected({**explicit,
                    "sorted_reverse_false_implicit_count": 1}, implicit))


class ConflictRegression35(unittest.TestCase):
    def test_list_conflict_drops_both_and_keeps_other_order(self):
        given = [entry("a", "custom_a"),
                 entry("리스트 컴프리헨션", "create_safe_comprehension_collection"),
                 entry("b", "custom_b"),
                 entry("리스트 누적 방식 사용", "create_safe_append_collection"),
                 entry("c", "custom_c")]
        self.assertEqual(action_names(_resolve_collection_actions(given)),
                         ["custom_a", "custom_b", "custom_c"])

    def test_dictionary_conflict_drops_both(self):
        given = [entry("a", "custom_a"),
                 entry("딕셔너리 컴프헨션", "create_safe_dict_comprehension"),
                 entry("b", "custom_b"),
                 entry("딕셔너리 기반 매핑 구조", "create_safe_dict_loop")]
        self.assertEqual(action_names(_resolve_dictionary_actions(given)),
                         ["custom_a", "custom_b"])

    def test_iteration_conflicts_fail_closed(self):
        cases = [
            ("create_direct_iteration", "create_index_iteration"),
            ("create_while_iteration", "create_direct_iteration"),
            ("create_while_iteration", "create_counted_while_to_for"),
        ]
        for left, right in cases:
            with self.subTest(left=left, right=right):
                given = [entry("a", "custom_a"), entry("loop", left),
                         entry("b", "custom_b"), entry("loop", right)]
                self.assertEqual(action_names(_resolve_iteration_actions(given)),
                                 ["custom_a", "custom_b"])

    def test_every_bidirectional_family_and_duplicate(self):
        for family, actions in _NEW_FAMILY_PAIRS.items():
            with self.subTest(family=family):
                left, right = sorted(actions)
                given = [entry("a", "custom_a"), entry(family, left),
                         entry("b", "custom_b"), entry(family, right)]
                self.assertEqual(action_names(_resolve_new_family_actions(given)),
                                 ["custom_a", "custom_b"])
                repeated = [entry("a", "custom_a"), entry(family, left),
                            entry("b", "custom_b"), entry(family, left)]
                self.assertEqual(action_names(_resolve_new_family_actions(repeated)),
                                 ["custom_a", left, "custom_b"])

    def test_policy_family_dedup_and_source_tag_provenance(self):
        self.assertEqual(len(TAG_ACTION_POLICIES), 32)
        for family, pair in SHARED_TAG_FAMILIES.items():
            with self.subTest(family=family):
                given = [entry(pair[0], TAG_ACTION_POLICIES[pair[0]]["mapped_action"]),
                         entry("other", "custom_a"),
                         entry(pair[1], TAG_ACTION_POLICIES[pair[1]]["mapped_action"]),
                         entry("other", "custom_b")]
                result = finalize_tag_action_policies(given)
                self.assertEqual(len(result), 3)
                self.assertEqual(action_names(result)[1:], ["custom_a", "custom_b"])
                self.assertEqual(result[0]["policy_family"], family)
                self.assertEqual(set(result[0]["policy_source_tags"]), set(pair))
                self.assertIn("policy_role", result[0])
                self.assertIn("policy_action", result[0])

    def test_compatible_iteration_order_preserved(self):
        given = [entry("a", "custom_a"),
                 entry("loop", "create_direct_iteration"),
                 entry("b", "custom_b"),
                 entry("loop", "create_counted_while_to_for"),
                 entry("c", "custom_c")]
        expected = ["custom_a", "create_direct_iteration", "custom_b",
                    "create_counted_while_to_for", "custom_c"]
        self.assertEqual(action_names(_resolve_iteration_actions(given)), expected)
        self.assertEqual(action_names(_resolve_iteration_actions(given)), expected)


if __name__ == "__main__":
    unittest.main()
