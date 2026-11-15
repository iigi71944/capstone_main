"""Batch 15 structural, non-executing conflict reconciliation tests."""
from __future__ import annotations

import unittest

from app.services.style_partial_conflict_service import (
    mark_partially_reverted_actions,
)


def code(a=1, b=2, c=3):
    return (f'def alpha():\n    return {a}\n\n'
            f'def beta():\n    return {b}\n\n'
            f'def gamma():\n    return {c}\n')


def ledger(n):
    return [{'tag': f'tag{i}', 'action': f'action{i}', 'status': 'applied'}
            for i in range(n)]


class PartialConflictTests(unittest.TestCase):
    def test_revert_alpha_but_keep_beta(self):
        snapshots = [code(), code(a=4), code(), code(b=5)]
        rows = ledger(3)
        self.assertEqual(mark_partially_reverted_actions(snapshots, rows), 2)
        self.assertEqual([r['status'] for r in rows],
                         ['cancelled_net_zero', 'cancelled_net_zero', 'applied'])

    def test_one_action_changes_two_scopes_only_one_reverted(self):
        snapshots = [code(), code(a=4, b=5), code(a=1, b=5)]
        rows = ledger(2)
        self.assertEqual(mark_partially_reverted_actions(snapshots, rows), 1)
        self.assertEqual([r['status'] for r in rows], ['applied', 'cancelled_net_zero'])
        # The first action retains a real change in beta, so do not label it cancelled.

    def test_revert_one_scope_then_change_another_same_action(self):
        snapshots = [code(), code(a=4), code(a=1, b=5)]
        rows = ledger(2)
        self.assertEqual(mark_partially_reverted_actions(snapshots, rows), 1)
        self.assertEqual([r['status'] for r in rows], ['cancelled_net_zero', 'applied'])

    def test_reverted_middle_snapshot_and_new_final(self):
        snapshots = [code(), code(a=4), code(a=5), code(a=4), code(a=4, b=7)]
        rows = ledger(4)
        self.assertEqual(mark_partially_reverted_actions(snapshots, rows), 2)
        self.assertEqual([r['status'] for r in rows],
                         ['applied', 'cancelled_net_zero', 'cancelled_net_zero', 'applied'])

    def test_independent_persistent_actions_not_cancelled(self):
        snapshots = [code(), code(a=4), code(a=4, b=5)]
        rows = ledger(2)
        self.assertEqual(mark_partially_reverted_actions(snapshots, rows), 0)
        self.assertEqual([r['status'] for r in rows], ['applied', 'applied'])

    def test_named_top_level_assignment_support(self):
        snapshots = ['a = 1\nb = 2\n', 'a = 3\nb = 2\n',
                     'a = 1\nb = 2\n', 'a = 1\nb = 4\n']
        rows = ledger(3)
        self.assertEqual(mark_partially_reverted_actions(snapshots, rows), 2)
        self.assertEqual(rows[2]['status'], 'applied')

    def test_unchanged_print_statement_is_allowed(self):
        suffix = '\nprint(alpha(), beta())\n'
        snapshots = [code() + suffix, code(a=4) + suffix,
                     code() + suffix, code(b=5) + suffix]
        rows = ledger(3)
        self.assertEqual(mark_partially_reverted_actions(snapshots, rows), 2)

    def test_changed_unidentified_statement_fails_closed(self):
        s = ['x = 1\nprint(1)\n', 'x = 2\nprint(1)\n',
             'x = 1\nprint(2)\n']
        rows = ledger(2)
        self.assertEqual(mark_partially_reverted_actions(s, rows), 0)
        self.assertTrue(all(r['status'] == 'applied' for r in rows))

    def test_inserted_statement_fails_closed(self):
        s = ['a = 1\n', 'a = 2\n', 'a = 1\nb = 2\n']
        rows = ledger(2)
        self.assertEqual(mark_partially_reverted_actions(s, rows), 0)

    def test_reordered_scopes_fails_closed(self):
        s = ['a = 1\nb = 2\n', 'a = 3\nb = 2\n', 'b = 2\na = 1\n']
        rows = ledger(2)
        self.assertEqual(mark_partially_reverted_actions(s, rows), 0)

    def test_duplicate_assignment_fails_closed(self):
        s = ['a = 1\na = 2\n', 'a = 3\na = 2\n', 'a = 1\na = 2\n']
        rows = ledger(2)
        self.assertEqual(mark_partially_reverted_actions(s, rows), 0)

    def test_changed_unstable_anchor_fails_closed(self):
        s = [code(), code(a=4), code().replace('def alpha', 'def other')]
        rows = ledger(2)
        self.assertEqual(mark_partially_reverted_actions(s, rows), 0)

    def test_unrecognized_only_fails_closed(self):
        s = ['print(1)\n', 'print(2)\n', 'print(1)\n']
        rows = ledger(2)
        self.assertEqual(mark_partially_reverted_actions(s, rows), 0)

    def test_invalid_syntax_fails_closed(self):
        s = [code(), 'def broken(:\n', code()]
        rows = ledger(2)
        self.assertEqual(mark_partially_reverted_actions(s, rows), 0)

    def test_misaligned_snapshots_rejected(self):
        with self.assertRaises(ValueError):
            mark_partially_reverted_actions([code()], ledger(2))

    def test_failed_step_must_not_change_ast(self):
        snapshots = [code(), code(a=4), code()]
        rows = ledger(2)
        rows[1]['status'] = 'no_safe_pattern'
        self.assertEqual(mark_partially_reverted_actions(snapshots, rows), 0)
        self.assertEqual(rows[0]['status'], 'applied')

    def test_already_cancelled_status_preserved(self):
        snapshots = [code(), code(a=4), code(), code(b=5)]
        rows = ledger(3)
        rows[0]['status'] = 'cancelled_net_zero'
        rows[1]['status'] = 'cancelled_net_zero'
        self.assertEqual(mark_partially_reverted_actions(snapshots, rows), 0)
        self.assertEqual(rows[2]['status'], 'applied')

    def test_only_one_action_no_new_cancellation(self):
        rows = ledger(1)
        self.assertEqual(mark_partially_reverted_actions([code(), code(a=4)], rows), 0)

    def test_crlf_preserved_as_source_only(self):
        snapshots = [code().replace('\n', '\r\n'), code(a=4).replace('\n','\r\n'),
                     code().replace('\n', '\r\n'), code(b=5).replace('\n','\r\n')]
        rows = ledger(3)
        self.assertEqual(mark_partially_reverted_actions(snapshots, rows), 2)

    def test_many_actions_fails_closed_without_rewriting(self):
        rows = ledger(64)
        snapshots = [code()] * 65
        self.assertEqual(mark_partially_reverted_actions(snapshots, rows), 0)
        self.assertTrue(all(item['status'] == 'applied' for item in rows))

    def test_large_code_fails_closed(self):
        source = '# ' + ('x' * 250_001) + '\n' + code()
        rows = ledger(2)
        self.assertEqual(mark_partially_reverted_actions([source] * 3, rows), 0)

    def test_non_code_changes_no_new_cancellation(self):
        a = code()
        b = '# comment\n' + code()
        rows = ledger(2)
        rows[0]['status'] = 'cancelled_net_zero'
        self.assertEqual(mark_partially_reverted_actions([a, b, a], rows), 0)


if __name__ == '__main__':
    unittest.main()
