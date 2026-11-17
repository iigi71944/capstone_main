"""Batch36-1: benchmark integrity and non-mutating reporting tests.

50-case real execution belongs to tools/audit_batch36_1.py; the full regression
suite should stay fast. Unit tests use injected providers, never execute mock code.
"""
import ast
import json
import unittest
from collections import Counter

from tools.batch36_1_cases import CASES, Case
from tools.audit_batch36_1 import evaluate_case, run_audit, summarize


class Batch36FixtureContractTests(unittest.TestCase):
    def test_exactly_fifty_cases(self):
        self.assertEqual(len(CASES), 50)

    def test_exactly_ten_groups_with_five_each(self):
        self.assertEqual(len(set(c.group for c in CASES)), 10)
        self.assertTrue(all(n == 5 for n in Counter(c.group for c in CASES).values()))

    def test_ids_names_and_sources_are_unique(self):
        self.assertEqual([c.case_id for c in CASES], [f"R{i:02d}" for i in range(1, 51)])
        self.assertEqual(len({(c.group, c.name) for c in CASES}), 50)
        self.assertEqual(len({(c.style_code, c.target_code) for c in CASES}), 50)

    def test_all_code_is_parseable_python(self):
        for case in CASES:
            with self.subTest(case=case.case_id):
                ast.parse(case.style_code)
                ast.parse(case.target_code)

    def test_no_external_library_or_network_or_file_write(self):
        for case in CASES:
            with self.subTest(case=case.case_id):
                for source in (case.style_code, case.target_code):
                    tree = ast.parse(source)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.Import, ast.ImportFrom)):
                            names = ([a.name.split('.')[0] for a in node.names]
                                     if isinstance(node, ast.Import)
                                     else [node.module.split('.')[0] if node.module else ''])
                            self.assertTrue(set(names) <= {"asyncio"})
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                            self.assertNotIn(node.func.id, {"open", "exec", "eval", "compile", "__import__"})

    def test_stdin_and_version_are_explicit(self):
        self.assertEqual(len([c for c in CASES if c.stdin is not None]), 1)
        self.assertTrue(all(c.version in {"v1", "legacy"} for c in CASES))
        self.assertGreaterEqual(len([c for c in CASES if c.version == "legacy"]), 1)


class Batch36ReportTests(unittest.TestCase):
    @staticmethod
    def providers(status="equivalent", change=True):
        def analyze(source):
            return {"syntax_tags": [{"tag": "want"}], "concept_tags": [], "metrics": {"function_count": 1}}
        def compare(style, source):
            return {"missing_syntax_tags": [{"tag": "want"}], "missing_concept_tags": [],
                    "style_metrics_info": {"status": "current_complete"}}
        def apply(**kwargs):
            after = kwargs["code"] + "\n# audit changed\n" if change else kwargs["code"]
            verification = ({"status": status,
                             "equivalent": True if status == "equivalent" else
                                           False if status == "different" else None}
                            if change else None)
            return (after, "summary", ["rule"] if change else [], [],
                    {"missing_syntax_tags": [], "missing_concept_tags": [],
                     "transform_diagnostics": {"counts": {"attempted": 1},
                                               "attempted_actions": [{"status": "applied"}],
                                               "omitted_actions": []}}, verification)
        return analyze, compare, apply

    def run_one(self, *, status="equivalent", change=True, strict=False):
        analyze, compare, apply = self.providers(status, change)
        return evaluate_case(CASES[0], strict_runtime_validation=strict,
                             analyze_fn=analyze, compare_fn=compare, apply_fn=apply)

    def test_equivalent_changed_code_is_verified(self):
        record = self.run_one()
        self.assertTrue(record["changed"])
        self.assertTrue(record["output_syntax_valid"])
        self.assertEqual(record["verification_status"], "equivalent")
        self.assertEqual(record["resolved_count"], 1)
        self.assertEqual(record["tag_progress_rate"], 1)
        self.assertEqual(record["errors"], [])

    def test_not_run_is_never_counted_as_verified(self):
        record = self.run_one(change=False)
        self.assertFalse(record["changed"])
        self.assertEqual(record["verification_status"], "not_run")
        summary = summarize([record])
        self.assertEqual(summary["changed_and_runtime_equivalent"], 0)
        self.assertIsNone(summary["runtime_verified_change_rate"])

    def test_unverified_change_is_reported_separately(self):
        record = self.run_one(status="not_verified")
        summary = summarize([record])
        self.assertEqual(summary["changed_but_runtime_not_verified"], 1)
        self.assertEqual(summary["changed_and_runtime_equivalent"], 0)
        self.assertEqual(record["errors"], [])

    def test_known_difference_not_rolled_back_is_a_failure(self):
        record = self.run_one(status="different")
        self.assertIn("known_runtime_difference_not_rolled_back", record["errors"])
        self.assertEqual(summarize([record])["failed_case_count"], 1)

    def test_strict_mode_rejects_unverified_change(self):
        record = self.run_one(status="not_verified", strict=True)
        self.assertIn("strict_mode_unverified_change", record["errors"])

    def test_all_records_are_serializable_and_report_does_not_mutate_fixtures(self):
        analyze, compare, apply = self.providers()
        before = list(CASES)
        report = run_audit(CASES[:2], analyze_fn=analyze,
                           compare_fn=compare, apply_fn=apply)
        self.assertEqual(report["case_count"], 2)
        self.assertEqual(report["summary"]["changed_and_runtime_equivalent"], 2)
        self.assertEqual(CASES, before)
        json.dumps(report, ensure_ascii=False)

    def test_actual_service_smoke_in_backend(self):
        # Only one real case here, keeping the 2,391-test baseline fast.
        # The 50-case evaluation is run explicitly as an independent audit.
        import importlib.util
        if importlib.util.find_spec("app") is None:
            self.skipTest("Full backend app is not available in the standalone package")
        record = evaluate_case(CASES[10])
        self.assertFalse(record["errors"], record)
        self.assertTrue(record["output_syntax_valid"])
        self.assertIn(record["verification_status"],
                      {"equivalent", "different", "not_verified", "not_run"})


if __name__ == "__main__":
    unittest.main()
