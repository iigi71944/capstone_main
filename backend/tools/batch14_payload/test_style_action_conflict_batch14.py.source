"""Batch 14: only surviving actions count as applied.

All transformers/verifiers are mocked in integration tests. No user code is
executed by these tests.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.style_action_conflict_service import mark_reverted_actions
from app.services import style_apply_service as svc

BASE = 'value = 1\n'
B = 'value = 2\n'
C = 'value = 3\n'
D = 'value = 4\n'
EQUIVALENT = {'status': 'equivalent', 'equivalent': True, 'message': 'ok'}


def _invoke(names, targets, verdict=EQUIVALENT):
    actions = [{'tag': name, 'action': name, 'reason': name} for name in names]
    transforms = {key: (lambda _code, value=value: value)
                  for key, value in targets.items()}
    with patch.object(svc, 'compare_style_with_target_code', return_value={}), \
         patch.object(svc, 'build_transform_plan', return_value={
             'actions': actions, 'compare_only': []}), \
         patch.object(svc, 'compare_after_transform', return_value={
             'missing_syntax_tags': [], 'missing_concept_tags': []}), \
         patch.object(svc, '_get_transform_function', side_effect=transforms.get), \
         patch.object(svc, 'verify_execution_equivalence', return_value=verdict):
        return svc.apply_coding_style(BASE, {})


class CheckpointUnitTests(unittest.TestCase):
    def test_a_b_revert_then_c_remains(self):
        results = [{'status': 'applied'} for _ in range(3)]
        n = mark_reverted_actions([BASE, B, BASE, C], results, normalize=lambda s: s)
        self.assertEqual(n, 2)
        self.assertEqual([r['status'] for r in results], [
            'cancelled_net_zero', 'cancelled_net_zero', 'applied'])

    def test_revert_to_middle_preserves_first_action(self):
        results = [{'status': 'applied'} for _ in range(3)]
        mark_reverted_actions([BASE, B, C, B], results, normalize=lambda s: s)
        self.assertEqual([r['status'] for r in results], [
            'applied', 'cancelled_net_zero', 'cancelled_net_zero'])

    def test_skipped_action_cannot_cause_false_rollback(self):
        results = [{'status':'applied'}, {'status':'no_safe_pattern'},
                   {'status':'applied'}, {'status':'applied'}]
        mark_reverted_actions([BASE, B, B, BASE, C], results, normalize=lambda s: s)
        self.assertEqual([r['status'] for r in results], [
            'cancelled_net_zero', 'no_safe_pattern', 'cancelled_net_zero', 'applied'])

    def test_multiple_independent_reversions(self):
        results = [{'status': 'applied'} for _ in range(5)]
        count = mark_reverted_actions([BASE,B,BASE,C,BASE,D], results, normalize=lambda s: s)
        self.assertEqual(count, 4)
        self.assertEqual(results[-1]['status'], 'applied')

    def test_all_surviving_actions_remain(self):
        results = [{'status':'applied'} for _ in range(3)]
        self.assertEqual(mark_reverted_actions([BASE,B,C,D], results, normalize=lambda s:s), 0)
        self.assertTrue(all(r['status']=='applied' for r in results))

    def test_invalid_alignment_fails_before_mutation(self):
        rows = [{'status':'applied'}]
        with self.assertRaises(ValueError):
            mark_reverted_actions([BASE], rows, normalize=lambda s:s)
        self.assertEqual(rows[0]['status'], 'applied')

    def test_normalized_syntax_compares_equivalent_snapshots(self):
        rows = [{'status':'applied'},{'status':'applied'}]
        mark_reverted_actions([BASE, B, 'value=1\n'], rows,
                              normalize=svc._normalize_code)
        self.assertEqual([r['status'] for r in rows],
                         ['cancelled_net_zero', 'cancelled_net_zero'])


class Batch14IntegrationTests(unittest.TestCase):
    def test_intermediate_reversal_then_new_change(self):
        result = _invoke(['first','undo','third'],
                         {'first':B, 'undo':BASE, 'third':C})
        self.assertEqual(result[0], C)
        self.assertIn('적용 1건, 생략 0건, 취소 2건', result[1])
        self.assertEqual(len(result[2]), 1)
        self.assertIn('third', result[2][0])
        self.assertNotIn('first', result[2][0])
        self.assertIn('first', ''.join(result[3]))
        self.assertIn('undo', ''.join(result[3]))

    def test_revert_to_middle_then_new_change(self):
        result = _invoke(['first','second','back','final'],
                         {'first':B,'second':C,'back':B,'final':D})
        self.assertEqual(result[0], D)
        self.assertIn('적용 2건, 생략 0건, 취소 2건', result[1])
        self.assertEqual(len(result[2]), 2)
        self.assertIn('first', result[2][0])
        self.assertIn('final', result[2][1])

    def test_skipped_action_preserved(self):
        result = _invoke(['first','missing','undo','final'],
                         {'first':B, 'undo':BASE, 'final':C})
        self.assertEqual(result[0], C)
        self.assertIn('적용 1건, 생략 1건, 취소 2건', result[1])
        self.assertEqual(len(result[2]), 1)

    def test_all_effects_survive_no_false_cancellation(self):
        result = _invoke(['first','second'], {'first':B,'second':C})
        self.assertEqual(result[0], C)
        self.assertIn('적용 2건, 생략 0건, 취소 0건', result[1])

    def test_final_net_zero_contract_preserved(self):
        result = _invoke(['first','undo'], {'first':B,'undo':BASE})
        self.assertEqual(result[0], BASE)
        self.assertEqual(result[2], [])
        self.assertIn('취소 2건', result[1])

    def test_verifier_different_true_is_malformed_and_rolls_back(self):
        result = _invoke(['first'], {'first': B},
                         {'status':'different','equivalent':True,'message':'bad'})
        self.assertEqual(result[0], BASE)
        self.assertEqual(result[5]['status'], 'not_verified')
        self.assertIsNone(result[5]['equivalent'])
        self.assertIn('취소 1건',result[1])

    def test_verifier_different_none_is_malformed_and_rolls_back(self):
        result = _invoke(['first'], {'first': B},
                         {'status':'different','equivalent':None,'message':'bad'})
        self.assertEqual(result[0], BASE)
        self.assertEqual(result[5]['status'], 'not_verified')
        self.assertIn('취소 1건',result[1])

    def test_genuine_difference_still_rolls_back(self):
        result = _invoke(['first'], {'first': B},
                         {'status':'different','equivalent':False,'message':'different'})
        self.assertEqual(result[0], BASE)
        self.assertEqual(result[5]['status'], 'different')
        self.assertIn('취소 1건',result[1])

    def test_six_element_contract_preserved(self):
        self.assertEqual(len(_invoke(['first'], {'first': B})), 6)


if __name__ == '__main__':
    unittest.main()
