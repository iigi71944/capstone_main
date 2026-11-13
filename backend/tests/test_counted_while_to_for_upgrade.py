"""Regression tests for counted while-to-for conversion and action wiring."""

import ast
import contextlib
import io
import unittest

from app.services.improvement.counted_while_to_for_service import (
    transform_counted_while_to_for,
)
from app.services.style_tag_transform_map_service import (
    get_create_action_for_tag,
    get_tag_transform_status,
)
from app.services.style_transform_plan_service import build_transform_plan


def _observe(code: str):
    scope = {"__name__": "__main__"}
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(compile(code, "<test>", "exec"), scope)
    return output.getvalue(), {k: v for k, v in scope.items() if k in {"i", "j", "result", "numbers"}}


def _matching(code: str):
    new = transform_counted_while_to_for(code)
    ast.parse(new)
    original_output, before = _observe(code)
    changed_output, after = _observe(new)
    assert original_output == changed_output, (original_output, changed_output)
    assert before == after, (before, after)
    return new


def _diff(style_syntax, target_syntax, missing_concept=None):
    return {
        "style_syntax_names": set(style_syntax),
        "target_syntax_names": set(target_syntax),
        "style_concept_names": set(),
        "target_concept_names": set(),
        "style_metrics": {},
        "target_analysis": {"metrics": {}},
        "missing_syntax_tags": [],
        "missing_concept_tags": missing_concept or [],
    }


class CountedWhileToForUpgradeTests(unittest.TestCase):
    def test_positive_increment(self):
        source = "i = 0\nwhile i < 4:\n    print(i)\n    i += 1\nprint(i)\n"
        new = _matching(source)
        self.assertIn("for i in range(i, 4):", new)
        self.assertIn("i += 1", new)

    def test_list_length_and_index(self):
        source = 'numbers = [10, 20, 30]\ni = 0\nwhile i < len(numbers):\n    print(numbers[i])\n    i += 1\nprint("final", i)\n'
        new = _matching(source)
        self.assertIn("for i in range(i, len(numbers)):", new)

    def test_inclusive_boundary(self):
        source = "i = 0\nresult = []\nwhile i <= 5:\n    result.append(i)\n    i += 2\nprint(result, i)\n"
        new = _matching(source)
        self.assertIn("range(i, (5) + 1, 2)", new)

    def test_decrement_and_reversed_compare(self):
        source = "i = 5\nresult = []\nwhile 0 < i:\n    result.append(i)\n    i -= 2\nprint(result, i)\n"
        new = _matching(source)
        self.assertIn("for i in range(i, 0, -2):", new)

    def test_decrement_inclusive(self):
        source = "i = 5\nwhile i >= 1:\n    print(i)\n    i -= 1\nprint(i)\n"
        new = _matching(source)
        self.assertIn("range(i, (1) - 1, -1)", new)

    def test_assignment_increment(self):
        source = "i = 1\nwhile i < 5:\n    print(i)\n    i = i + 2\nprint(i)\n"
        new = _matching(source)
        self.assertIn("range(i, 5, 2)", new)

    def test_assignment_increment_reversed(self):
        source = "i = 1\nwhile i < 4:\n    print(i)\n    i = 1 + i\nprint(i)\n"
        new = _matching(source)
        self.assertIn("range(i, 4)", new)

    def test_assignment_decrement(self):
        source = "i = 4\nwhile i > 0:\n    print(i)\n    i = i - 2\nprint(i)\n"
        new = _matching(source)
        self.assertIn("range(i, 0, -2)", new)

    def test_limit_variable(self):
        source = "i = 0\nlimit = 4\nwhile i < limit:\n    print(i)\n    i += 1\nprint(i)\n"
        new = _matching(source)
        self.assertIn("range(i, limit)", new)

    def test_break_keeps_final_value(self):
        source = "i = 0\nwhile i < 9:\n    if i == 3:\n        break\n    print(i)\n    i += 1\nprint('end', i)\n"
        new = _matching(source)
        self.assertIn("for i in range(i, 9):", new)

    def test_while_else(self):
        source = "i = 0\nwhile i < 3:\n    print(i)\n    i += 1\nelse:\n    print('done')\nprint(i)\n"
        new = _matching(source)
        self.assertIn("for i in range(i, 3):", new)
        self.assertIn("else:", new)

    def test_zero_iterations(self):
        source = "i = 10\nwhile i < 4:\n    print(i)\n    i += 1\nprint(i)\n"
        new = _matching(source)
        self.assertIn("for i in range(i, 4):", new)

    def test_keep_comments_and_formatting(self):
        source = "# heading\ni = 0\nwhile i < 2:  # counting\n    # comment inside\n    print(i)\n    i += 1\n# footer\n"
        new = _matching(source)
        self.assertIn("# heading", new)
        self.assertIn("# comment inside", new)
        self.assertIn("for i in range(i, 2):  # counting", new)
        self.assertIn("# footer", new)

    def test_header_comment_with_colon_is_preserved(self):
        source = "i = 0\nwhile i < 2:  # note: stop at two\n    print(i)\n    i += 1\n"
        updated = _matching(source)
        self.assertIn("for i in range(i, 2):  # note: stop at two", updated)

    def test_skip_continue(self):
        source = "i = 0\nwhile i < 3:\n    if i > 1:\n        continue\n    i += 1\n"
        self.assertEqual(transform_counted_while_to_for(source), source)

    def test_skip_modified_length_source(self):
        source = "items = [1, 2]\ni = 0\nwhile i < len(items):\n    items.append(9)\n    i += 1\n"
        self.assertEqual(transform_counted_while_to_for(source), source)

    def test_skip_modified_limit(self):
        source = "i = 0\nlimit = 2\nwhile i < limit:\n    limit += 1\n    i += 1\n"
        self.assertEqual(transform_counted_while_to_for(source), source)

    def test_skip_unbounded_while(self):
        source = "while True:\n    break\n"
        self.assertEqual(transform_counted_while_to_for(source), source)

    def test_skip_step_in_wrong_direction(self):
        source = "i = 0\nwhile i < 5:\n    i -= 1\n"
        self.assertEqual(transform_counted_while_to_for(source), source)

    def test_skip_range_shadowing(self):
        source = "range = 8\ni = 0\nwhile i < 3:\n    i += 1\n"
        self.assertEqual(transform_counted_while_to_for(source), source)

    def test_does_not_change_for_statement(self):
        source = "for i in range(3):\n    print(i)\n"
        self.assertEqual(transform_counted_while_to_for(source), source)

    def test_multiple_while(self):
        source = "i = 0\nwhile i < 2:\n    print(i)\n    i += 1\nj = 3\nwhile j > 0:\n    print(j)\n    j -= 1\n"
        new = _matching(source)
        self.assertEqual(new.count("for "), 2)

    def test_plan_only_when_for_is_preferred(self):
        diff = _diff(["for문"], ["while문"])
        actions = build_transform_plan(diff)["actions"]
        self.assertIn("create_counted_while_to_for", [item["action"] for item in actions])
        diff = _diff(["while문"], ["for문"], [{"tag": "반복문 중심 구조"}])
        result = build_transform_plan(diff)
        self.assertNotIn("create_counted_while_to_for", [item["action"] for item in result["actions"]])
        self.assertIn("반복문 중심 구조", result["compare_only"])

    def test_prior_actions_remain(self):
        expected = {
            "직접 반복 사용": "create_direct_iteration",
            "인덱스 기반 반복 사용": "create_index_iteration",
            "while문": "create_while_iteration",
            "f-string 사용": "create_fstring_style",
            "return문": "create_return_structure",
        }
        for tag, action in expected.items():
            self.assertEqual(get_create_action_for_tag(tag), action)
        self.assertEqual(get_tag_transform_status("반복문 중심 구조"), "linked")


if __name__ == "__main__":
    unittest.main()
