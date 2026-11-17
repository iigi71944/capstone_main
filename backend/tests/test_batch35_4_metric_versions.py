"""Batch 35-4 regression: versioned 81-metric saved styles and incomplete data.

No changes to existing transformer implementations or six-result API contract.
"""
import ast
import copy
import json
import unittest

from app.services.metric_service import calculate_metrics
from app.services.style_metric_snapshot_service import (
    METRICS_SCHEMA_VERSION,
    metric_names,
    normalize_style_metric_snapshot,
)
from app.services.style_diff_service import compare_style_with_target_code
from app.services.style_transform_plan_service import build_transform_plan
from app.services.style_apply_service import apply_coding_style
from app.schemas.style_apply import CodingStylePayload


class Batch35MetricSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.metrics = calculate_metrics(ast.parse(""))

    def test_current_metric_schema_81(self):
        self.assertEqual(METRICS_SCHEMA_VERSION, 1)
        self.assertEqual(len(metric_names()), 81)
        self.assertEqual(set(self.metrics), set(metric_names()))

    def test_full_current_is_allowed(self):
        snapshot, info = normalize_style_metric_snapshot(
            {"metrics_version": 1, "metrics": self.metrics})
        self.assertEqual(snapshot, self.metrics)
        self.assertEqual(info["status"], "current_complete")
        self.assertEqual(info["observed_count"], 81)
        self.assertTrue(info["automatic_transforms_allowed"])
        self.assertEqual(info["missing_keys"], [])

    def test_old_unversioned_complete_remains_compatible(self):
        _, info = normalize_style_metric_snapshot({"metrics": self.metrics})
        self.assertEqual(info["status"], "legacy_complete")
        self.assertIsNone(info["stored_version"])
        self.assertTrue(info["automatic_transforms_allowed"])

    def test_old_unversioned_partial_preserves_observations_not_imputed_zero(self):
        observed = {"function_count": 2, "return_count": 0}
        snapshot, info = normalize_style_metric_snapshot({"metrics": observed})
        self.assertEqual(snapshot, observed)
        self.assertEqual(info["status"], "legacy_partial")
        self.assertTrue(info["automatic_transforms_allowed"])
        self.assertEqual(info["observed_count"], 2)
        self.assertEqual(len(info["missing_keys"]), 79)
        self.assertNotIn("while_index_loop_count", snapshot)
        self.assertNotIn("function_count", info["missing_keys"])

    def test_versioned_partial_is_blocked(self):
        saved = dict(self.metrics)
        del saved["sorted_call_count"]
        snapshot, info = normalize_style_metric_snapshot(
            {"metrics_version": 1, "metrics": saved})
        self.assertNotIn("sorted_call_count", snapshot)
        self.assertEqual(info["status"], "incomplete_versioned")
        self.assertEqual(info["missing_keys"], ["sorted_call_count"])
        self.assertFalse(info["automatic_transforms_allowed"])

    def test_missing_metric_object_is_explicitly_incomplete(self):
        snapshot, info = normalize_style_metric_snapshot({"metrics_version": 1})
        self.assertEqual(snapshot, {})
        self.assertEqual(info["status"], "incomplete_versioned")
        self.assertEqual(len(info["missing_keys"]), 81)
        self.assertFalse(info["automatic_transforms_allowed"])

    def test_malformed_container_blocks_without_exceptions(self):
        for raw in (None, 12, [1, 2], "bad"):
            with self.subTest(metrics=raw):
                snapshot, info = normalize_style_metric_snapshot(
                    {"metrics": raw})
                self.assertEqual(snapshot, {})
                self.assertEqual(info["status"], "invalid_snapshot")
                self.assertFalse(info["automatic_transforms_allowed"])

    def test_invalid_numeric_values_rejected_not_coerced(self):
        for invalid in (True, False, -1, "1", 1.5, None, float("nan")):
            with self.subTest(value=invalid):
                metrics = dict(self.metrics)
                metrics["function_count"] = invalid
                snapshot, info = normalize_style_metric_snapshot(
                    {"metrics_version": 1, "metrics": metrics})
                self.assertNotIn("function_count", snapshot)
                self.assertIn("function_count", info["invalid_keys"])
                self.assertFalse(info["automatic_transforms_allowed"])

    def test_future_and_invalid_version_block_auto_transforms(self):
        for version in (2, 99, 0, -1, True, "1", "future", 1.5):
            with self.subTest(version=version):
                _, info = normalize_style_metric_snapshot(
                    {"metrics_version": version, "metrics": self.metrics})
                self.assertEqual(info["status"], "unsupported_version")
                self.assertFalse(info["automatic_transforms_allowed"])

    def test_unknown_keys_do_not_leak_into_transform_metrics(self):
        with_extra = dict(self.metrics)
        with_extra["not_a_real_metric"] = 999
        snapshot, info = normalize_style_metric_snapshot(
            {"metrics_version": 1, "metrics": with_extra})
        self.assertEqual(snapshot, self.metrics)
        self.assertEqual(info["unknown_keys"], ["not_a_real_metric"])
        self.assertTrue(info["automatic_transforms_allowed"])

    def test_does_not_mutate_input_and_json_serializable(self):
        source = {"metrics_version": 1, "metrics": dict(self.metrics)}
        original = copy.deepcopy(source)
        snapshot, info = normalize_style_metric_snapshot(source)
        snapshot["function_count"] = 500
        info["missing_keys"].append("fake")
        self.assertEqual(source, original)
        self.assertIsInstance(json.dumps(info), str)


class Batch35MetricIntegrationTests(unittest.TestCase):
    def test_comparison_keeps_version_provenance(self):
        style = {"syntax_tags": [], "concept_tags": [],
                 "metrics": {"function_count": 2}, "metrics_version": 1}
        compared = compare_style_with_target_code(style, "x = 1\n")
        self.assertEqual(compared["style_metrics"], {"function_count": 2})
        self.assertEqual(compared["style_metrics_info"]["status"], "incomplete_versioned")
        self.assertEqual(compared["target_analysis"]["metrics"]["assign_count"], 1)
        self.assertNotIn("style_metrics_info", style)

    def test_incomplete_versioned_snapshot_fails_closed_without_altering_tags(self):
        diff = compare_style_with_target_code({
            "syntax_tags": [{"tag": "리스트 컴프리헨션", "count": 1}],
            "concept_tags": [],
            "metrics": {"function_count": 1}, "metrics_version": 1,
        }, "x = [1, 2]\n")
        plan = build_transform_plan(diff)
        self.assertEqual(plan["actions"], [])
        self.assertEqual(plan["omitted_actions"], [])
        self.assertEqual(plan["compare_only"], [])
        self.assertEqual(len(plan["not_selected_tags"]), 1)
        self.assertEqual(plan["not_selected_tags"][0]["reason_code"],
                         "untrusted_metric_snapshot")

    def test_unknown_future_version_fails_closed(self):
        diff = compare_style_with_target_code({
            "syntax_tags": [{"tag": "for문", "count": 1}],
            "concept_tags": [],
            "metrics": calculate_metrics(ast.parse("for x in [1]:\n    print(x)\n")),
            "metrics_version": 999,
        }, "x = 1\n")
        plan = build_transform_plan(diff)
        self.assertEqual(plan["actions"], [])
        self.assertTrue(plan["not_selected_tags"])

    def test_apply_six_result_contract_and_reason_record(self):
        code = "x = 1\n"
        style = {"syntax_tags": [], "concept_tags": [],
                 "metrics": {"if_count": 1}, "metrics_version": 1}
        result = apply_coding_style(code, style)
        self.assertEqual(len(result), 6)
        self.assertEqual(result[0], code)
        self.assertTrue(any("저장 메트릭" in note for note in result[3]))
        self.assertIn("transform_diagnostics", result[4])
        self.assertEqual(result[4]["style_metrics_info"]["status"],
                         "incomplete_versioned")

    def test_old_payload_omitting_version_and_metrics_parses(self):
        model = CodingStylePayload(
            id="legacy", name="old", description="", syntax_tags=[],
            concept_tags=[], created_at="2026-01-01")
        self.assertEqual(model.metrics, {})
        self.assertIsNone(model.metrics_version)

    def test_new_payload_persists_declared_version_and_raw_values(self):
        model = CodingStylePayload(
            id="current", name="new", description="", syntax_tags=[],
            concept_tags=[], created_at="2026-11-17", metrics={"if_count": True},
            metrics_version=1)
        self.assertEqual(model.model_dump()["metrics_version"], 1)
        # Never coerce bool True to integer 1 before snapshot validation.
        self.assertIs(model.model_dump()["metrics"]["if_count"], True)
        _, info = normalize_style_metric_snapshot(model.model_dump())
        self.assertEqual(info["status"], "invalid_snapshot")


if __name__ == "__main__":
    unittest.main()
