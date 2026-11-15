"""Registry / planner / dispatcher checks for four newly linked syntax tags."""
import unittest

from app.services.style_tag_transform_map_service import (
    CREATE_ACTION_BY_TAG, get_tag_transform_status, get_create_action_for_tag,
)
from app.services.style_transform_plan_service import build_transform_plan
from app.services.style_apply_service import _get_transform_function
from app.services.style_transform_audit_service import audit_style_registry


EXPECTED = {
    'range 사용': 'create_safe_literal_range',
    '논리 연산': 'create_safe_nested_boolean',
    '멤버십 연산': 'create_safe_known_membership',
    'sorted 사용': 'create_sort_style',
}


def plan(style_metrics, target_metrics):
    diff = {
        'missing_syntax_tags': [], 'missing_concept_tags': [],
        'style_syntax_names': set(), 'style_concept_names': set(),
        'target_syntax_names': set(), 'target_concept_names': set(),
        'style_metrics': style_metrics,
        'target_analysis': {'metrics': target_metrics},
    }
    return [item['action'] for item in build_transform_plan(diff)['actions']]


class Batch9WiringTests(unittest.TestCase):
    def test_four_tags_linked(self):
        for tag, action in EXPECTED.items():
            with self.subTest(tag=tag):
                self.assertEqual(get_tag_transform_status(tag), 'linked')
                self.assertEqual(get_create_action_for_tag(tag), action)
                self.assertIsNotNone(_get_transform_function(action))

    def test_registry_audit_no_errors(self):
        self.assertEqual(audit_style_registry()['issues'], [])

    def test_range_selected_from_saved_existing_metrics(self):
        self.assertIn('create_safe_literal_range',
                      plan({'range_call_count': 1}, {'range_call_count': 0}))

    def test_membership_selected_from_saved_existing_metrics(self):
        self.assertIn('create_safe_known_membership',
                      plan({'membership_op_count': 3}, {'membership_op_count': 0}))

    def test_logical_selected_from_saved_existing_metrics(self):
        self.assertIn('create_safe_nested_boolean',
                      plan({'bool_op_count': 1}, {'bool_op_count': 0}))

    def test_sort_selected_without_saved_concept(self):
        selected = plan({'sorted_call_count': 1, 'sort_method_call_count': 0},
                        {'sorted_call_count': 0, 'sort_method_call_count': 1})
        self.assertIn('create_sort_style', selected)
        self.assertEqual(selected.count('create_sort_style'), 1)

    def test_no_invented_preference_without_saved_evidence(self):
        selected = plan({}, {'range_call_count': 0,
                              'membership_op_count': 0,
                              'bool_op_count': 0,
                              'sort_method_call_count': 1})
        for action in EXPECTED.values():
            self.assertNotIn(action, selected)

    def test_saved_metrics_unchanged_by_plan(self):
        saved = {'range_call_count': 2, 'bool_op_count': 1}
        target = {'range_call_count': 0, 'bool_op_count': 0}
        before = saved.copy(), target.copy()
        plan(saved, target)
        self.assertEqual((saved, target), before)


if __name__ == '__main__':
    unittest.main()
