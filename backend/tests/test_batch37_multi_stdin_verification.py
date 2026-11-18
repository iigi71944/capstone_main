"""Batch37: every submitted stdin must be independently observed, up to 8.
Run: python -m unittest tests.test_batch37_multi_stdin_verification -v
"""
import unittest
from pydantic import ValidationError

from app.services.execution_validation_service import verify_execution_equivalence
from app.schemas.style_apply import StyleApplyRequest, ExecutionVerification


CODE = '''name = input()
score = int(input())
if score >= 60:
    status = "PASS"
else:
    status = "RETRY"
print(name + ": " + status)
'''

EQUIVALENT_CODE = '''name = input()
score = int(input())
status = "PASS" if score >= 60 else "RETRY"
print(name + ": " + status)
'''

BUGGY_CODE = '''name = input()
score = int(input())
status = "PASS" if score > 60 else "RETRY"
print(name + ": " + status)
'''


class MultiStdinVerificationTests(unittest.TestCase):
    def test_two_independent_inputs(self):
        result = verify_execution_equivalence(
            CODE, EQUIVALENT_CODE, stdin="민수\n85",
            stdin_cases=["민수\n85", "영희\n20"],
        )
        self.assertEqual(result["status"], "equivalent")
        self.assertTrue(result["equivalent"])
        rows = result["stdin_case_results"]
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["case_number"] for r in rows], [1, 2])
        self.assertEqual([r["original"]["stdout"].strip() for r in rows],
                         ["민수: PASS", "영희: RETRY"])
        self.assertEqual([r["transformed"]["stdout"].strip() for r in rows],
                         ["민수: PASS", "영희: RETRY"])
        self.assertTrue(all(row["equivalent"] for row in rows))
        self.assertEqual(result["original"]["stdout"], rows[0]["original"]["stdout"])
        self.assertEqual(result["transformed"]["stdout"], rows[0]["transformed"]["stdout"])
        self.assertEqual(ExecutionVerification.model_validate(result).stdin_case_results[1].stdin,
                         "영희\n20")

    def test_second_input_detects_difference_even_when_first_passes(self):
        result = verify_execution_equivalence(
            CODE, BUGGY_CODE, stdin_cases=["민수\n85", "영희\n60"],
        )
        self.assertEqual(result["status"], "different")
        self.assertIs(result["equivalent"], False)
        self.assertEqual([r["status"] for r in result["stdin_case_results"]],
                         ["equivalent", "different"])

    def test_up_to_eight_cases(self):
        inputs = [f"이름{i}\n{i * 10}" for i in range(8)]
        result = verify_execution_equivalence(CODE, EQUIVALENT_CODE, stdin_cases=inputs)
        self.assertEqual(len(result["stdin_case_results"]), 8)
        self.assertEqual(result["status"], "equivalent")

    def test_unverified_does_not_get_labeled_equivalent(self):
        original = "x = input()"
        result = verify_execution_equivalence(original, original, stdin_cases=["hello"])
        self.assertEqual(result["status"], "not_verified")
        self.assertIsNone(result["equivalent"])
        self.assertEqual(result["stdin_case_results"][0]["status"], "not_verified")

    def test_invalid_size_rejected(self):
        with self.assertRaises(ValueError):
            verify_execution_equivalence(CODE, CODE, stdin_cases=["A\n5"] * 9)
        with self.assertRaises(ValueError):
            verify_execution_equivalence(CODE, CODE, stdin_cases=[])

    def test_invalid_stdin_rejected(self):
        with self.assertRaises(ValueError):
            verify_execution_equivalence(CODE, CODE, stdin_cases=["x" * 8193])
        with self.assertRaises(ValueError):
            verify_execution_equivalence(CODE, CODE, stdin_cases=["a\n" * 129])

    def test_mismatch_between_shared_and_first_input_rejected(self):
        with self.assertRaises(ValueError):
            verify_execution_equivalence(CODE, CODE, stdin="A\n10",
                                         stdin_cases=["B\n15"])

    def test_legacy_single_input_response_stays_legacy(self):
        result = verify_execution_equivalence(CODE, EQUIVALENT_CODE, stdin="민수\n85")
        self.assertEqual(result["status"], "equivalent")
        self.assertNotIn("stdin_case_results", result)

    def test_named_function_and_two_inputs(self):
        original = "def add_one(x):\n    return x + 1\nprint(input())\n"
        result = verify_execution_equivalence(
            original, original, function_cases=[{"function": "add_one", "args": [4], "kwargs": {}}],
            stdin="A", stdin_cases=["A", "B"],
        )
        self.assertEqual(result["status"], "equivalent")
        self.assertEqual(len(result["stdin_case_results"]), 2)
        self.assertEqual(len(result["function_verification"]["cases"]), 1)

    def test_unverified_stdin_cannot_be_overridden_by_function(self):
        original = "def add_one(x):\n    return x + 1\ninput()\n"
        result = verify_execution_equivalence(
            original, original, function_cases=[{"function": "add_one", "args": [4], "kwargs": {}}],
            stdin_cases=["A"],
        )
        self.assertEqual(result["status"], "not_verified")
        self.assertIsNone(result["function_verification"])

    def test_request_schema_limits_count(self):
        payload = {
            "language": "python", "code": CODE,
            "style": {"id": "x", "name": "x", "description": "x", "syntax_tags": [],
                      "concept_tags": [], "metrics": {}, "created_at": "2026-11-18"},
            "stdin": "A\n5", "stdin_cases": ["A\n5"] * 8,
        }
        self.assertEqual(len(StyleApplyRequest.model_validate(payload).stdin_cases), 8)
        with self.assertRaises(ValidationError):
            StyleApplyRequest.model_validate({**payload, "stdin_cases": ["A\n5"] * 9})


if __name__ == "__main__":
    unittest.main()
