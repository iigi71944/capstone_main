"""Regression tests for truthful status reporting without executing user code."""

import unittest
from unittest.mock import patch

from app.services import style_apply_service as service
from app.services.style_action_outcome_service import (
    summarize_action_outcomes,
    format_action_outcome_summary,
    format_cancelled_action_warnings,
)

BASE = "value = 1\n"
CHANGED = "value = 2\n"
EQUIVALENT = {"status": "equivalent", "equivalent": True, "message": "ok"}
DIFFERENT = {"status": "different", "equivalent": False, "message": "different"}
UNKNOWN = {"status": "not_verified", "equivalent": None, "message": "restricted"}


def item(action, tag=None):
    return {"tag": tag or action, "action": action, "reason": "테스트 규칙"}


def invoke(actions, implementations=None, verdict=EQUIVALENT, *, strict=False, cases=None):
    implementations = implementations or {}

    def lookup(name):
        return implementations.get(name)

    with patch.object(service, "compare_style_with_target_code", return_value={}), \
         patch.object(service, "build_transform_plan", return_value={"actions": actions, "compare_only": []}), \
         patch.object(service, "compare_after_transform", return_value={"missing_syntax_tags": [], "missing_concept_tags": []}), \
         patch.object(service, "_get_transform_function", side_effect=lookup), \
         patch.object(service, "verify_execution_equivalence", return_value=verdict):
        return service.apply_coding_style(BASE, {}, function_cases=cases,
                                          strict_runtime_validation=strict)


class PureOutcomeTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(summarize_action_outcomes([])["total"], 0)

    def test_empty_summary(self):
        self.assertIn("액션이 없습니다", format_action_outcome_summary(summarize_action_outcomes([])))

    def test_category_counts(self):
        rows = [
            {"tag":"A","action":"a","status":"applied"},
            {"tag":"B","action":"b","status":"no_safe_pattern"},
            {"tag":"C","action":"c","status":"rolled_back"},
        ]
        result = summarize_action_outcomes(rows)
        self.assertEqual((result['total'],result['applied'],result['skipped'],result['cancelled']), (3,1,1,1))

    def test_order_preserved(self):
        report = summarize_action_outcomes([{"tag":"B","status":"applied"},{"tag":"A","status":"invalid_result"}])
        self.assertEqual([x['tag'] for x in report['items']],['B','A'])

    def test_unknown_result_fail_closed(self):
        result = summarize_action_outcomes([{"tag":"hi","status":"unexpected"}])
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(result['applied'], 0)

    def test_malformed_rows_ignored(self):
        r = summarize_action_outcomes([{},None,"bad",{"status":None,"tag":123}])
        self.assertEqual(r['total'],2)
        self.assertEqual(r['items'][-1]['tag'],"")

    def test_cancel_warning_descriptive(self):
        r = summarize_action_outcomes([{"status":"rolled_back","tag":"리스트 컴프리헨션"}])
        notes = format_cancelled_action_warnings(r)
        self.assertEqual(len(notes),1)
        self.assertIn('리스트 컴프리헨션', notes[0])

    def test_applied_not_warned(self):
        self.assertEqual(format_cancelled_action_warnings(
            summarize_action_outcomes([{"status":"applied", "tag":"x"}])), [])

    def test_summary_arithmetic(self):
        s = format_action_outcome_summary(summarize_action_outcomes([
            {"status":"applied"},{"status":"transformer_missing"},{"status":"rolled_back"}]))
        for span in ('3건','적용 1건','생략 1건','취소 1건'):
            self.assertIn(span,s)

    def test_all_skip_reason_statuses(self):
        for status in ('no_safe_pattern','transformer_missing','transformer_error',
                       'empty_result','invalid_result'):
            with self.subTest(status=status):
                r = summarize_action_outcomes([{"status":status}])
                self.assertEqual(r['skipped'],1)
                self.assertEqual(r['applied'],0)


class IntegrationOutcomeTests(unittest.TestCase):
    def test_successful_action(self):
        out = invoke([item('change')], {'change': lambda _: CHANGED})
        self.assertEqual(out[0], CHANGED)
        self.assertIn('적용 1건',out[1])
        self.assertEqual(len(out[2]),1)
        self.assertIn('적용 완료',out[2][0])

    def test_skipped_no_pattern(self):
        out = invoke([item('noop')], {'noop': lambda code: code})
        self.assertEqual(out[0], BASE)
        self.assertIn('생략 1건',out[1])
        self.assertEqual(out[2],[])
        self.assertIn('안전하게 변환', ''.join(out[3]))

    def test_missing_transformer(self):
        out = invoke([item('not-registered')])
        self.assertIn('생략 1건',out[1])
        self.assertIn('변환기',''.join(out[3]))

    def test_bad_empty_transformer(self):
        out = invoke([item('blank')], {'blank':lambda _: ''})
        self.assertEqual(out[0],BASE)
        self.assertIn('생략 1건',out[1])

    def test_invalid_python(self):
        out = invoke([item('invalid')],{'invalid':lambda _:'def bad(\n'})
        self.assertEqual(out[0],BASE)
        self.assertIn('생략 1건',out[1])

    def test_raised_transformer_exception(self):
        def bad(_): raise RuntimeError('bad')
        out = invoke([item('bad')], {'bad':bad})
        self.assertEqual(out[0],BASE)
        self.assertIn('생략 1건',out[1])

    def test_runtime_difference_rollback(self):
        out = invoke([item('change','집계')], {'change': lambda _: CHANGED}, DIFFERENT)
        self.assertEqual(out[0], BASE)
        self.assertEqual(out[2],[])
        self.assertIn('취소 1건',out[1])
        self.assertIn('집계', ''.join(out[3]))

    def test_malformed_verifier_rollback(self):
        out = invoke([item('change')], {'change':lambda _:CHANGED}, verdict=None)
        self.assertEqual(out[0],BASE)
        self.assertIn('취소 1건',out[1])

    def test_unverified_default_retained_not_called_verified(self):
        out = invoke([item('change')], {'change':lambda _:CHANGED}, UNKNOWN)
        self.assertEqual(out[0],CHANGED)
        self.assertIn('적용 1건',out[1])
        self.assertIn('검증되지 않은', ''.join(out[3]))

    def test_unverified_strict_rollback(self):
        out = invoke([item('change')], {'change':lambda _:CHANGED}, UNKNOWN, strict=True)
        self.assertEqual(out[0],BASE)
        self.assertIn('취소 1건',out[1])

    def test_no_actions(self):
        out = invoke([])
        self.assertEqual(out[0],BASE)
        self.assertIn('액션이 없습니다',out[1])
        self.assertEqual(len(out),6)

    def test_combined_apply_and_skip(self):
        out = invoke([item('change'),item('noop')],{
            'change':lambda _:CHANGED,'noop':lambda code:code})
        self.assertEqual(out[0],CHANGED)
        self.assertIn('적용 1건, 생략 1건',out[1])
        self.assertEqual(len(out[2]),1)

    def test_second_transform_reverts_first(self):
        def change(_):return CHANGED
        def revert(_):return BASE
        out = invoke([item('change','처음'),item('revert','복원')],{
            'change':change,'revert':revert})
        self.assertEqual(out[0],BASE)
        self.assertEqual(out[2],[])
        self.assertIn('취소 2건',out[1])
        self.assertIn('처음', ''.join(out[3]))
        self.assertIn('복원', ''.join(out[3]))

    def test_six_item_contract(self):
        self.assertEqual(len(invoke([item('change')],{'change':lambda _:CHANGED})),6)

    def test_runtime_verifier_called_for_function_case_no_change(self):
        out = invoke([],cases=[{'input':1}])
        self.assertEqual(out[0],BASE)
        self.assertEqual(out[2],[])

    def test_cancelled_not_in_applied_rules(self):
        out = invoke([item('change')],{'change':lambda _:CHANGED},DIFFERENT)
        self.assertFalse(any('적용 완료' in s for s in out[2]))

    def test_status_count_labels_not_verified_assertion(self):
        out = invoke([item('change')],{'change':lambda _:CHANGED},UNKNOWN)
        self.assertIn('실행 결과 또는 함수 반환값의 동일성을 확인하지 못했습니다',out[1])

    def test_no_user_code_execution_in_report_module(self):
        r=summarize_action_outcomes([{"tag":"x","status":"applied"}])
        self.assertEqual(r['applied'],1)


if __name__=='__main__':
    unittest.main()
