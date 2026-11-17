"""35-3: transparent conflicts, skips and rollback reasons without API breakage."""
import json
import unittest
from unittest.mock import patch

from app.services.style_action_diagnostic_service import (
    trace_plan_filter,
    build_transform_diagnostics,
)
from app.services.style_transform_plan_service import build_transform_plan
from app.services.style_apply_service import apply_coding_style


def item(tag, action):
    return {"tag": tag, "action": action, "reason": "original plan reason"}


class Batch35_3TraceTests(unittest.TestCase):
    def test_stage_records_opposing_directions_and_preserves_inputs(self):
        before = [item("A", "custom_a"),
                  item("리스트", "create_safe_append_collection"),
                  item("B", "custom_b"),
                  item("리스트", "create_safe_comprehension_collection")]
        after = [before[0], before[2]]
        original = json.dumps(before, ensure_ascii=False)
        omitted = trace_plan_filter(before, after, "collection")
        self.assertEqual(len(omitted), 2)
        self.assertTrue(all(x["reason_code"] == "collection_preference_conflict"
                            for x in omitted))
        self.assertTrue(all(x["reason"] and x["status"] == "omitted" for x in omitted))
        self.assertEqual(json.dumps(before, ensure_ascii=False), original)

    def test_duplicates_get_duplicate_not_conflict_reason(self):
        a = item("X", "create_safe_next_guard")
        b = item("Y", "create_safe_next_guard")
        reasons = trace_plan_filter([a, b], [a], "bidirectional_families")
        self.assertEqual(len(reasons), 1)
        self.assertEqual(reasons[0]["reason_code"], "duplicate_action")
        self.assertEqual(reasons[0]["tag"], "Y")

    def test_real_plan_records_filtered_actions_without_changing_decision(self):
        initial = [item("append", "create_safe_append_collection"),
                   item("custom", "custom_a"),
                   item("comprehension", "create_safe_comprehension_collection")]
        diff = {
            "style_metrics": {}, "target_analysis": {"metrics": {}},
            "style_syntax_names": set(), "style_concept_names": set(),
            "target_syntax_names": set(), "target_concept_names": set(),
            "missing_syntax_tags": [], "missing_concept_tags": [],
        }
        with patch("app.services.style_transform_plan_service._explicit_reverse_actions", return_value=initial):
            plan = build_transform_plan(diff)
        self.assertEqual([x["action"] for x in plan["actions"]], ["custom_a"])
        self.assertEqual(len(plan["omitted_actions"]), 2)
        self.assertTrue(all(x["stage"] == "collection" for x in plan["omitted_actions"]))
        self.assertEqual([x["action"] for x in initial], [
            "create_safe_append_collection", "custom_a", "create_safe_comprehension_collection",
        ])

    def test_real_plan_dictionary_conflict_reason(self):
        initial = [item("dict-comp", "create_safe_dict_comprehension"),
                   item("unrelated", "custom_b"),
                   item("dict-loop", "create_safe_dict_loop")]
        diff = {
            "style_metrics": {}, "target_analysis": {"metrics": {}},
            "style_syntax_names": set(), "style_concept_names": set(),
            "target_syntax_names": set(), "target_concept_names": set(),
            "missing_syntax_tags": [], "missing_concept_tags": [],
        }
        with patch("app.services.style_transform_plan_service._explicit_reverse_actions", return_value=initial):
            plan = build_transform_plan(diff)
        self.assertEqual([x["action"] for x in plan["actions"]], ["custom_b"])
        self.assertEqual({x["reason_code"] for x in plan["omitted_actions"]},
                         {"dictionary_preference_conflict"})

    def test_real_plan_unregistered_compare_only_reason(self):
        diff = {
            "style_metrics": {}, "target_analysis": {"metrics": {}},
            "style_syntax_names": set(), "style_concept_names": set(),
            "target_syntax_names": set(), "target_concept_names": set(),
            "missing_syntax_tags": [{"tag": "__batch35_unregistered_tag__"}],
            "missing_concept_tags": [],
        }
        plan = build_transform_plan(diff)
        self.assertEqual(plan["compare_only"], ["__batch35_unregistered_tag__"])
        self.assertEqual(plan["compare_only_details"][0]["reason_code"], "no_registered_transformer")
        report = build_transform_diagnostics(plan, [])
        self.assertEqual(report["compare_only_tags"][0]["reason_code"], "no_registered_transformer")

    def test_metric_gated_tag_non_selection_is_distinct_from_attempt(self):
        diff = {
            "style_metrics": {}, "target_analysis": {"metrics": {}},
            "style_syntax_names": set(), "style_concept_names": set(),
            "target_syntax_names": set(), "target_concept_names": set(),
            "missing_syntax_tags": [{"tag": "기본 매개변수"}],
            "missing_concept_tags": [],
        }
        plan = build_transform_plan(diff)
        self.assertFalse(any(x["tag"] == "기본 매개변수" for x in plan["actions"]))
        result = build_transform_diagnostics(plan, [])
        entry = next(x for x in result["not_selected_tags"] if x["tag"] == "기본 매개변수")
        self.assertEqual(entry["reason_code"], "selection_conditions_unmet")
        self.assertEqual(result["counts"]["not_selected"], 1)
        self.assertEqual(result["counts"]["attempted"], 0)

    def test_report_status_reasons_json_and_no_mutation(self):
        results = [
            {**item("A", "a"), "status": "no_safe_pattern", "plan_reason": "observed preference"},
            {**item("B", "b"), "status": "transformer_error"},
            {**item("C", "c"), "status": "cancelled_net_zero"},
            {**item("D", "d"), "status": "applied"},
        ]
        before = json.dumps(results)
        plan = {"compare_only": ["missing"], "omitted_actions": [{"status": "omitted"}]}
        report = build_transform_diagnostics(plan, results)
        self.assertEqual(report["counts"], {
            "omitted": 1, "attempted": 4, "not_applied": 3, "compare_only": 1,
            "not_selected": 0,
        })
        self.assertEqual(report["attempted_actions"][0]["plan_reason"], "observed preference")
        self.assertEqual(report["attempted_actions"][2]["reason_code"], "cancelled_by_later_action")
        self.assertEqual(report["compare_only_tags"][0]["status"], "compare_only")
        self.assertEqual(json.dumps(results), before)
        json.dumps(report, ensure_ascii=False)

    def test_runtime_rollback_reason_distinguishes_difference(self):
        r = [{"tag": "X", "action": "x", "status": "rolled_back"}]
        differing = build_transform_diagnostics({}, r, {"status": "different", "equivalent": False})
        unverified = build_transform_diagnostics({}, r, {"status": "not_verified", "equivalent": None})
        self.assertEqual(differing["attempted_actions"][0]["reason_code"], "runtime_difference")
        self.assertEqual(unverified["attempted_actions"][0]["reason_code"], "runtime_unverified")

    def test_unknown_stage_fails_closed(self):
        with self.assertRaises(ValueError):
            trace_plan_filter([], [], "future-unregistered-stage")


class Batch35_3ApplyIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.diff = {
            "style_metrics": {}, "target_analysis": {"metrics": {}},
            "style_syntax_names": set(), "style_concept_names": set(),
            "target_syntax_names": set(), "target_concept_names": set(),
            "missing_syntax_tags": [], "missing_concept_tags": [],
        }

    def test_existing_six_value_contract_and_no_pattern_detail(self):
        plan = {"actions": [item("테스트", "test_action")],
                "compare_only": ["추적 전용"],
                "omitted_actions": [{"tag": "Z", "action": "z", "status": "omitted",
                                     "stage": "iteration", "reason_code": "iteration_preference_conflict",
                                     "reason": "충돌"}]}
        with patch("app.services.style_apply_service.compare_style_with_target_code", return_value=self.diff), \
             patch("app.services.style_apply_service.build_transform_plan", return_value=plan), \
             patch("app.services.style_apply_service._get_transform_function", return_value=lambda code: code), \
             patch("app.services.style_apply_service.compare_after_transform", return_value={"target_analysis": {"metrics": {}}}):
            result = apply_coding_style("value = 1\n", {"metrics": {}})
        self.assertEqual(len(result), 6)
        self.assertEqual(result[0], "value = 1\n")
        diag = result[4]["transform_diagnostics"]
        self.assertEqual(diag["attempted_actions"][0]["reason_code"], "no_safe_pattern")
        self.assertEqual(diag["attempted_actions"][0]["plan_reason"], "original plan reason")
        self.assertEqual(diag["counts"]["omitted"], 1)
        self.assertEqual(diag["counts"]["compare_only"], 1)

    def test_runtime_rollback_preserves_original_code_and_records_reason(self):
        plan = {"actions": [item("테스트", "test_action")], "compare_only": [], "omitted_actions": []}
        with patch("app.services.style_apply_service.compare_style_with_target_code", return_value=self.diff), \
             patch("app.services.style_apply_service.build_transform_plan", return_value=plan), \
             patch("app.services.style_apply_service._get_transform_function", return_value=lambda code: "value = 2\n"), \
             patch("app.services.style_apply_service.compare_after_transform", return_value={"target_analysis": {"metrics": {}}}), \
             patch("app.services.style_apply_service.verify_execution_equivalence", return_value={
                 "status": "different", "equivalent": False, "message": "different", "function_verification": None,
             }):
            result = apply_coding_style("value = 1\n", {"metrics": {}})
        self.assertEqual(result[0], "value = 1\n")
        self.assertEqual(result[4]["transform_diagnostics"]["attempted_actions"][0]["reason_code"], "runtime_difference")
        self.assertFalse(result[2])


if __name__ == "__main__":
    unittest.main()
