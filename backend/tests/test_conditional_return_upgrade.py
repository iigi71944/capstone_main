
"""Regression tests for safe condition/return transformations and style plans."""

import ast
import unittest

from app.services.improvement.conditional_return_service import (
    transform_to_boolean_return_style,
    transform_to_conditional_expression_style,
    transform_to_if_statement_style,
)
from app.services.style_tag_transform_map_service import (
    get_create_action_for_tag,
    get_tag_transform_status,
)
from app.services.style_transform_plan_service import build_transform_plan


def _run_function(code: str, function: str, *args):
    namespace = {}
    exec(compile(code, "<regression>", "exec"), namespace)
    return namespace[function](*args)


def _diff(style_metrics, target_metrics, missing_syntax=None, missing_concept=None):
    return {
        "style_metrics": style_metrics,
        "target_analysis": {"metrics": target_metrics},
        "missing_syntax_tags": missing_syntax or [],
        "missing_concept_tags": missing_concept or [],
        "style_syntax_names": set(),
        "style_concept_names": set(),
        "target_syntax_names": set(),
        "target_concept_names": set(),
    }


class ConditionalReturnUpgradeTests(unittest.TestCase):
    def test_expand_conditional_assignment(self):
        original = '''def grade(score):
    result = "합격" if score >= 60 else "불합격"
    return result
'''
        transformed = transform_to_if_statement_style(original)
        self.assertIn("if score >= 60:", transformed)
        self.assertIn('result = "합격"', transformed)
        for value in (0, 59, 60, 100):
            self.assertEqual(_run_function(original, "grade", value),
                             _run_function(transformed, "grade", value))
        self.assertEqual(transform_to_if_statement_style(transformed), transformed)

    def test_expand_conditional_return(self):
        original = '''def choose(flag):
    return 1 if flag else 0
'''
        transformed = transform_to_if_statement_style(original)
        self.assertIn("if flag:", transformed)
        for flag in (True, False, None, [], [1]):
            self.assertEqual(_run_function(original, "choose", flag),
                             _run_function(transformed, "choose", flag))

    def test_collapse_if_assignment(self):
        original = '''def grade(score):
    if score >= 60:
        result = "합격"
    else:
        result = "불합격"
    return result
'''
        transformed = transform_to_conditional_expression_style(original)
        self.assertIn(" if (score >= 60) else ", transformed)
        for value in (20, 60, 95):
            self.assertEqual(_run_function(original, "grade", value),
                             _run_function(transformed, "grade", value))
        self.assertEqual(transform_to_conditional_expression_style(transformed), transformed)

    def test_collapse_if_return(self):
        original = '''def fee(member):
    if member:
        return 3000
    else:
        return 5000
'''
        transformed = transform_to_conditional_expression_style(original)
        self.assertIn("return (3000) if (member) else (5000)", transformed)
        for value in (True, False, "yes", ""):
            self.assertEqual(_run_function(original, "fee", value),
                             _run_function(transformed, "fee", value))

    def test_boolean_return_preserves_type_for_truthy_nonbools(self):
        original = '''def eligible(value):
    if value:
        return True
    else:
        return False
'''
        transformed = transform_to_boolean_return_style(original)
        self.assertIn("return not not (value)", transformed)
        for value in (True, False, 12, 0, "yes", "", [1], []):
            before = _run_function(original, "eligible", value)
            after = _run_function(transformed, "eligible", value)
            self.assertIs(type(after), bool)
            self.assertEqual(before, after)

    def test_false_true_boolean_pattern(self):
        original = '''def should_stop(value):
    if value:
        return False
    else:
        return True
'''
        transformed = transform_to_boolean_return_style(original)
        self.assertIn("return not (value)", transformed)
        for value in (True, False, 1, 0, "x", ""):
            self.assertEqual(_run_function(original, "should_stop", value),
                             _run_function(transformed, "should_stop", value))

    def test_skip_comment_inside_replacement_but_keep_unrelated_comments(self):
        code = '''# explain the calculation
value = 1 if active else 2  # inline user note
'''
        self.assertEqual(transform_to_if_statement_style(code), code)
        safe_code = '''# keep this header
value = 1 if active else 2
# keep this footer
'''
        self.assertIn("# keep this header", transform_to_if_statement_style(safe_code))
        self.assertIn("# keep this footer", transform_to_if_statement_style(safe_code))

    def test_skip_semicolon_trailing_code(self):
        code = "x = 1 if flag else 2; y = 3\n"
        self.assertEqual(transform_to_if_statement_style(code), code)

    def test_unsupported_multiple_branch_statements_unchanged(self):
        code = '''def run(value):
    if value:
        print("a")
        return 1
    else:
        return 2
'''
        self.assertEqual(transform_to_conditional_expression_style(code), code)
        ast.parse(code)

    def test_saved_if_style_plans_if_expansion(self):
        diff = _diff(
            {"if_count": 1, "if_exp_count": 0},
            {"if_count": 0, "if_exp_count": 1},
            missing_syntax=[{"tag": "if문"}],
        )
        result = build_transform_plan(diff)
        self.assertEqual([item["action"] for item in result["actions"]], ["create_if_statement"])

    def test_saved_ternary_style_plans_condensing(self):
        diff = _diff(
            {"if_count": 0, "if_exp_count": 1},
            {"if_count": 1, "if_exp_count": 0},
        )
        result = build_transform_plan(diff)
        self.assertIn("create_conditional_expression", [x["action"] for x in result["actions"]])

    def test_saved_direct_return_style_plans_boolean_rewrite(self):
        diff = _diff(
            {"if_count": 0, "if_exp_count": 0, "return_count": 1},
            {"if_count": 1, "if_exp_count": 0, "return_count": 2},
        )
        result = build_transform_plan(diff)
        self.assertIn("create_return_structure", [x["action"] for x in result["actions"]])

    def test_old_transformer_links_preserved(self):
        old_links = {
            "직접 반복 사용": "create_direct_iteration",
            "리스트 누적 방식 사용": "create_append_collection",
            "정렬 중심 구조": "create_sort_style",
            "f-string 사용": "create_fstring_style",
            "함수 중심 코드 구조": "create_function_structure",
        }
        for tag, action in old_links.items():
            self.assertEqual(get_create_action_for_tag(tag), action)
        for tag in ("if문", "조건문 중심 구조", "삼항 조건식", "return문"):
            self.assertEqual(get_tag_transform_status(tag), "linked")


if __name__ == "__main__":
    unittest.main()
