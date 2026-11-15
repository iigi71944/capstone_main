"""Batch 15 saved-style pipeline checks (all transformers/verifiers mocked)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services import style_apply_service as svc


def code(a=1, b=2):
    return (f'def alpha():\n    return {a}\n\n'
            f'def beta():\n    return {b}\n')

BASE = code()
EQUIVALENT = {'status': 'equivalent', 'equivalent': True, 'message': 'fixed fixture'}
DIFFERENT = {'status': 'different', 'equivalent': False, 'message': 'fixed fixture'}


def _apply(targets, verdict=EQUIVALENT):
    actions = [{'tag': name, 'action': name, 'reason': name} for name, _ in targets]
    outcomes = {name: (lambda original, result=result: result)
                for name, result in targets if result is not None}
    with patch.object(svc, 'compare_style_with_target_code', return_value={}), \
         patch.object(svc, 'build_transform_plan', return_value={
             'actions': actions, 'compare_only': []}), \
         patch.object(svc, 'compare_after_transform', return_value={
             'missing_syntax_tags': [], 'missing_concept_tags': []}), \
         patch.object(svc, '_get_transform_function', side_effect=outcomes.get), \
         patch.object(svc, 'verify_execution_equivalence', return_value=verdict):
        return svc.apply_coding_style(BASE, {})


class Batch15PipelineTests(unittest.TestCase):
    def test_one_scope_reverted_other_final_kept(self):
        result = _apply([('alpha', code(a=3)), ('undo', BASE),
                         ('beta', code(b=4))])
        self.assertEqual(result[0], code(b=4))
        self.assertIn('적용 1건, 생략 0건, 취소 2건', result[1])
        self.assertEqual(len(result[2]), 1)
        self.assertIn('beta', result[2][0])
        self.assertTrue(any('alpha' in note for note in result[3]))

    def test_partial_reversion_without_full_file_checkpoint(self):
        result = _apply([('changealpha', code(a=3)),
                         ('changebeta', code(a=3, b=4)),
                         ('undoalpha', code(b=4))])
        self.assertEqual(result[0], code(b=4))
        self.assertIn('적용 1건, 생략 0건, 취소 2건', result[1])
        self.assertEqual(len(result[2]), 1)
        self.assertIn('changebeta', result[2][0])

    def test_combined_action_keeps_partial_surviving_effect(self):
        result = _apply([('both', code(a=3, b=4)),
                         ('undoalpha', code(b=4))])
        self.assertEqual(result[0], code(b=4))
        self.assertIn('적용 1건, 생략 0건, 취소 1건', result[1])
        self.assertIn('both', result[2][0])
        self.assertFalse(any('undoalpha' in note for note in result[2]))

    def test_different_runtime_rolls_back_all_survivors(self):
        result = _apply([('alpha', code(a=3)), ('undo', BASE),
                         ('beta', code(b=4))], verdict=DIFFERENT)
        self.assertEqual(result[0], BASE)
        self.assertEqual(result[2], [])
        self.assertIn('취소 3건', result[1])

    def test_unmatched_region_preserves_old_reporting(self):
        changed = BASE + 'print(1)\n'
        result = _apply([('changealpha', code(a=3)),
                         ('untracked', changed)])
        self.assertEqual(result[0], changed)
        self.assertIn('적용 2건', result[1])

    def test_six_item_return_contract_unchanged(self):
        self.assertEqual(len(_apply([('alpha', code(a=3))])), 6)

    def test_missing_transformer_is_not_counted_applied(self):
        result = _apply([('alpha', code(a=3)), ('missing', None)])
        self.assertIn('적용 1건, 생략 1건, 취소 0건', result[1])


if __name__ == '__main__':
    unittest.main()
