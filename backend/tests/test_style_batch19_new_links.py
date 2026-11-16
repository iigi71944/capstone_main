"""Batch 19: independent positive and safety tests for two new links.

Only trusted literals are executed by this test suite. Neither the rule nor
its audit executes arbitrary user-supplied code.
"""
import ast
import unittest
from app.services.improvement.safe_comparison_batch19_service import (
    transform_operator_comparison_to_syntax as transform_comparison,
)
from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_transform_map_service import get_create_action_for_tag
from app.services.style_transform_plan_service import build_transform_plan


class ComparisonTagTriplets(unittest.TestCase):
    def test_basic(self):
        src = 'import operator\nflag = operator.eq(3, 3)\n'
        self.assertEqual(transform_comparison(src), 'import operator\nflag = (3 == 3)\n')

    def test_additional(self):
        src = "import operator\na = operator.ne('a', 'b')  # keep\n"
        self.assertEqual(transform_comparison(src), "import operator\na = ('a' != 'b')  # keep\n")

    def test_complex(self):
        src = 'import operator\nfirst = operator.lt(3, 4)\nsecond = operator.ge(10, 9)\n'
        after = transform_comparison(src)
        self.assertIn('first = (3 < 4)', after)
        self.assertIn('second = (10 >= 9)', after)


class FunctionCallTagTriplets(unittest.TestCase):
    def _check(self, expr: str, action: str):
        src = 'import operator\nresult = ' + expr + '\n'
        fn = _get_transform_function('create_safe_operator_call')
        self.assertTrue(callable(fn))
        after = fn(src)
        self.assertIn(action, after)
        self.assertNotEqual(after, src)
        ast.parse(after)

    def test_basic(self):
        self._check('3 + 4', 'operator.add(')

    def test_additional(self):
        self._check('9 - 2', 'operator.sub(')

    def test_complex(self):
        self._check('7 * (2 + 1)', 'operator.mul(')


class Batch19Safety(unittest.TestCase):
    def test_no_operator_import(self):
        src = 'flag = operator.eq(1, 2)\n'
        self.assertEqual(transform_comparison(src), src)

    def test_import_after_use(self):
        src = 'flag = operator.eq(1, 2)\nimport operator\n'
        self.assertEqual(transform_comparison(src), src)

    def test_rebound_operator(self):
        src = 'import operator\noperator = 4\nflag = operator.eq(1, 2)\n'
        self.assertEqual(transform_comparison(src), src)

    def test_monkeypatch_attribute(self):
        src = 'import operator\noperator.eq = lambda a, b: False\nflag = operator.eq(1, 1)\n'
        self.assertEqual(transform_comparison(src), src)

    def test_side_effects_not_rewritten(self):
        src = 'import operator\nflag = operator.eq(f(), 2)\n'
        self.assertEqual(transform_comparison(src), src)

    def test_name_operands_not_rewritten(self):
        src = 'import operator\nflag = operator.eq(x, y)\n'
        self.assertEqual(transform_comparison(src), src)

    def test_nested_call_not_rewritten(self):
        src = 'import operator\nif operator.eq(1, 1):\n    pass\n'
        self.assertEqual(transform_comparison(src), src)

    def test_keyword_args_not_rewritten(self):
        src = 'import operator\nflag = operator.eq(a=1, b=2)\n'
        self.assertEqual(transform_comparison(src), src)

    def test_multiline_with_comment_not_rewritten(self):
        src = 'import operator\nflag = operator.eq(\n    1,  # comment\n    1,\n)\n'
        self.assertEqual(transform_comparison(src), src)

    def test_string_preserved_with_unicode(self):
        src = 'import operator\n답 = operator.eq("한글", "한글")\n'
        result = transform_comparison(src)
        self.assertIn('답 = ("한글" == "한글")', result)

    def test_crlf_preserved(self):
        src = 'import operator\r\nflag = operator.eq(1, 1)\r\n'
        self.assertEqual(transform_comparison(src), 'import operator\r\nflag = (1 == 1)\r\n')

    def test_unsupported_comparison_safe(self):
        src = 'import operator\nflag = operator.is_(1, 1)\n'
        self.assertEqual(transform_comparison(src), src)

    def test_invalid_python_unmodified(self):
        src = 'def bad(\n'
        self.assertEqual(transform_comparison(src), src)

    def test_double_import_not_rewritten(self):
        src = 'import operator\nimport operator\nflag = operator.eq(1, 2)\n'
        self.assertEqual(transform_comparison(src), src)

    def test_registry_and_dispatch(self):
        self.assertEqual(get_create_action_for_tag('비교 연산'), 'create_safe_operator_comparison')
        self.assertEqual(get_create_action_for_tag('함수 호출'), 'create_safe_operator_call')
        self.assertTrue(callable(_get_transform_function('create_safe_operator_comparison')))

    def test_plan_uses_preexisting_metrics(self):
        diff = {
            'missing_syntax_tags': [], 'missing_concept_tags': [],
            'style_syntax_names': set(), 'style_concept_names': set(),
            'target_syntax_names': set(), 'target_concept_names': set(),
            'style_metrics': {'compare_count': 1, 'call_count': 2},
            'target_analysis': {'metrics': {'compare_count': 0, 'call_count': 1,
                                           'bin_op_count': 2, 'import_count': 1}},
        }
        actions = {a['action'] for a in build_transform_plan(diff)['actions']}
        self.assertIn('create_safe_operator_comparison', actions)
        # Function-call target already has a call so no new call is generated.
        self.assertNotIn('create_safe_operator_call', actions)

    def test_plan_no_preference(self):
        diff = {
            'missing_syntax_tags': [], 'missing_concept_tags': [],
            'style_syntax_names': set(), 'style_concept_names': set(),
            'target_syntax_names': set(), 'target_concept_names': set(),
            'style_metrics': {},
            'target_analysis': {'metrics': {'bin_op_count': 2, 'import_count': 1,
                                           'call_count': 3}},
        }
        actions = {a['action'] for a in build_transform_plan(diff)['actions']}
        self.assertNotIn('create_safe_operator_comparison', actions)
        self.assertNotIn('create_safe_operator_call', actions)


if __name__ == '__main__':
    unittest.main()
