"""Regression checks for explicit function-result display and unchanged-code tests.

Run inside the capstone backend container after applying the upgrade:
    docker compose exec -T backend python -m unittest discover -s tests -p test_function_return_upgrade.py -v
"""

import unittest

from app.services.execution_validation_service import verify_execution_equivalence
from app.services.function_result_validation_service import verify_function_results
from app.services.style_apply_service import apply_coding_style
from app.services.style_diff_service import analyze_code_style


SOURCE = '''def show_result(name, score):
    if score >= 60:
        status = "합격"
    else:
        status = "불합격"
    greeting = "{}님".format(name)
    message = "시험 결과: {}".format(status)
    return greeting + " - " + message
'''

CONVERTED = '''def show_result(name, score):
    if score >= 60:
        status = "합격"
    else:
        status = "불합격"
    greeting = f"{name}님"
    message = f"시험 결과: {status}"
    return greeting + " - " + message
'''


class FunctionResultUpgradeTest(unittest.TestCase):
    def test_returns_real_values_for_two_inputs(self):
        cases = [
            {"function": "show_result", "args": ["민수", 90], "kwargs": {}},
            {"function": "show_result", "args": ["영희", 40], "kwargs": {}},
        ]
        report = verify_function_results(SOURCE, CONVERTED, cases)
        self.assertEqual(report["status"], "equivalent")
        self.assertEqual(len(report["cases"]), 2)

        for case, expected in zip(
            report["cases"],
            ["민수님 - 시험 결과: 합격", "영희님 - 시험 결과: 불합격"],
        ):
            self.assertEqual(case["status"], "equivalent")
            self.assertEqual(case["original_result"]["kind"], "value")
            self.assertEqual(case["original_result"]["value"]["type"], "str")
            self.assertEqual(case["original_result"]["value"]["value"], expected)
            self.assertEqual(case["transformed_result"]["value"]["value"], expected)

    def test_function_verification_when_no_style_change(self):
        cases = [{"function": "show_result", "args": ["민수", 90], "kwargs": {}}]
        comparison = verify_execution_equivalence(SOURCE, SOURCE, cases)
        self.assertEqual(comparison["status"], "equivalent")
        self.assertIsNotNone(comparison.get("function_verification"))
        self.assertEqual(
            comparison["function_verification"]["cases"][0]["original_result"]["value"]["value"],
            "민수님 - 시험 결과: 합격",
        )

        analysis = analyze_code_style(SOURCE)
        style = {
            "id": "test-style",
            "name": "Original style",
            "description": "Test style",
            "syntax_tags": analysis["syntax_tags"],
            "concept_tags": analysis["concept_tags"],
            "metrics": analysis["metrics"],
            "created_at": "test",
        }
        result = apply_coding_style(SOURCE, style, cases)
        self.assertIsNotNone(result[-1])
        self.assertIsNotNone(result[-1].get("function_verification"))

    def test_none_result_is_displayed_not_suppressed(self):
        source = "def empty():\n    return None\n"
        report = verify_function_results(
            source, source, [{"function": "empty", "args": [], "kwargs": {}}]
        )
        self.assertEqual(report["status"], "equivalent")
        value = report["cases"][0]["original_result"]["value"]
        self.assertEqual(value, {"type": "NoneType", "value": None})


if __name__ == "__main__":
    unittest.main()
