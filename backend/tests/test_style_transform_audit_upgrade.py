"""Read-only coverage audit and iteration-preference conflict regression tests."""

import itertools
import unittest
from unittest.mock import patch

from app.services.style_tag_transform_map_service import (
    CREATE_ACTION_BY_TAG,
    PLANNED_TAG_FAMILY,
    get_create_action_for_tag,
    get_tag_transform_status,
)
from app.services.style_transform_plan_service import build_transform_plan
from app.services.style_transform_audit_service import (
    INTERNAL_ACTIONS,
    audit_style_registry,
    audit_saved_style_plan,
)


def diff(*, missing_syntax=(), missing_concept=(), style_syntax=(),
         style_concept=(), target_syntax=(), target_concept=(),
         style_metrics=None, target_metrics=None):
    return {
        "missing_syntax_tags": [{"tag": name} for name in missing_syntax],
        "missing_concept_tags": [{"tag": name} for name in missing_concept],
        "style_syntax_names": set(style_syntax),
        "style_concept_names": set(style_concept),
        "target_syntax_names": set(target_syntax),
        "target_concept_names": set(target_concept),
        "style_metrics": style_metrics or {},
        "target_analysis": {"metrics": target_metrics or {}},
    }


def actions(d):
    return [item["action"] for item in build_transform_plan(d)["actions"]]


class RegistryAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = audit_style_registry()

    def test_no_registry_wiring_issues(self):
        self.assertEqual(self.report["issues"], [])
        self.assertEqual(self.report["status"], "ok")

    def test_statuses_cover_all_known_tags(self):
        s = self.report["summary"]
        self.assertEqual(s["all_tags"], s["linked_tags"] + s["planned_tags"] + s["compare_only_tags"])

    def test_syntax_and_concept_counts_are_positive(self):
        s = self.report["summary"]
        self.assertGreater(s["syntax_tags"], 0)
        self.assertGreater(s["concept_tags"], 0)

    def test_each_tag_has_exactly_one_status(self):
        statuses = self.report["tag_statuses"]
        seen = set()
        for names in statuses.values():
            for name in names:
                self.assertNotIn(name, seen)
                seen.add(name)
        self.assertEqual(len(seen), self.report["summary"]["all_tags"])

    def test_all_linked_public_actions_in_dispatcher(self):
        registered = self.report["dispatcher"]
        for tag, action in CREATE_ACTION_BY_TAG.items():
            with self.subTest(tag=tag, action=action):
                self.assertIn(action, registered)

    def test_all_safe_internal_actions_in_dispatcher(self):
        for action in INTERNAL_ACTIONS:
            with self.subTest(action=action):
                self.assertIn(action, self.report["dispatcher"])

    def test_all_planned_tags_marked_planned(self):
        for tag in PLANNED_TAG_FAMILY:
            with self.subTest(tag=tag):
                self.assertEqual(get_tag_transform_status(tag), "planned")

    def test_unknown_tag_stays_unknown(self):
        self.assertEqual(get_tag_transform_status("등록되지 않은 테스트 태그"), "unknown")

    def test_list_public_names_preserved(self):
        self.assertEqual(get_create_action_for_tag("리스트 누적 방식 사용"), "create_append_collection")
        self.assertEqual(get_create_action_for_tag("리스트 컴프리헨션"), "create_comprehension_collection")

    def test_dict_public_names_preserved(self):
        self.assertEqual(get_create_action_for_tag("딕셔너리 기반 매핑 구조"), "create_mapping_style")
        self.assertEqual(get_create_action_for_tag("딕셔너리 컴프리헨션"), "create_dict_comprehension")

    def test_detect_unimplemented_public_action(self):
        with patch.dict(CREATE_ACTION_BY_TAG, {"리스트 컴프리헨션": "missing_action"}):
            report = audit_style_registry()
        self.assertTrue(any(i["code"] == "LINKED_ACTION_MISSING" for i in report["issues"]))

    def test_detect_undeclared_public_tag(self):
        with patch.dict(CREATE_ACTION_BY_TAG, {"누락된 테스트 규칙": "create_filter_style"}):
            report = audit_style_registry()
        self.assertTrue(any(i["code"] == "UNDECLARED_LINKED_TAG" for i in report["issues"]))

    def test_report_does_not_execute_source(self):
        self.assertIn("정적", self.report["note"])

    def test_public_registry_not_mutated_by_audit(self):
        before = dict(CREATE_ACTION_BY_TAG)
        audit_style_registry()
        self.assertEqual(before, CREATE_ACTION_BY_TAG)


class IterationPlanTests(unittest.TestCase):
    def test_direct_only(self):
        self.assertEqual(actions(diff(missing_concept=["직접 반복 사용"])), ["create_direct_iteration"])

    def test_index_only(self):
        self.assertEqual(actions(diff(missing_concept=["인덱스 기반 반복 사용"])), ["create_index_iteration"])

    def test_while_only(self):
        self.assertEqual(actions(diff(missing_syntax=["while문"])), ["create_while_iteration"])

    def test_direct_and_index_fail_closed(self):
        self.assertEqual(actions(diff(missing_concept=["직접 반복 사용", "인덱스 기반 반복 사용"])), [])

    def test_direct_and_index_reverse_order_fail_closed(self):
        self.assertEqual(actions(diff(missing_concept=["인덱스 기반 반복 사용", "직접 반복 사용"])), [])

    def test_direct_and_index_other_tag_preserved(self):
        self.assertEqual(actions(diff(missing_concept=["직접 반복 사용", "인덱스 기반 반복 사용", "정렬 중심 구조"])), ["create_sort_style"])

    def test_duplicate_index_concepts_select_once(self):
        self.assertEqual(actions(diff(missing_concept=["인덱스 기반 반복 사용", "인덱싱 중심 구조"])), ["create_index_iteration"])

    def test_duplicate_index_reversed_select_once(self):
        self.assertEqual(actions(diff(missing_concept=["인덱싱 중심 구조", "인덱스 기반 반복 사용"])), ["create_index_iteration"])

    def test_duplicate_tag_items_select_once(self):
        self.assertEqual(actions(diff(missing_concept=["직접 반복 사용", "직접 반복 사용"])), ["create_direct_iteration"])

    def test_while_conflicts_direct(self):
        self.assertEqual(actions(diff(missing_syntax=["while문"], missing_concept=["직접 반복 사용"])), [])

    def test_while_conflicts_index(self):
        self.assertEqual(actions(diff(missing_syntax=["while문"], missing_concept=["인덱스 기반 반복 사용"])), [])

    def test_while_conflicts_index_but_sort_remains(self):
        self.assertEqual(actions(diff(missing_syntax=["while문"], missing_concept=["인덱스 기반 반복 사용", "정렬 중심 구조"])), ["create_sort_style"])

    def test_counted_while_and_direct_can_coexist(self):
        result = actions(diff(missing_concept=["직접 반복 사용"],
                              style_syntax=["for문"], target_syntax=["while문"]))
        self.assertEqual(result, ["create_counted_while_to_for", "create_direct_iteration"])

    def test_counted_while_and_index_can_coexist(self):
        result = actions(diff(missing_concept=["인덱스 기반 반복 사용"],
                              style_syntax=["for문"], target_syntax=["while문"]))
        self.assertEqual(result, ["create_counted_while_to_for", "create_index_iteration"])

    def test_counted_while_does_not_run_if_saved_while_present(self):
        self.assertEqual(actions(diff(style_syntax=["for문", "while문"], target_syntax=["while문"])), [])

    def test_unrelated_actions_keep_original_order(self):
        result = actions(diff(missing_concept=["정렬 중심 구조", "직접 반복 사용", "데이터 집계 구조"]))
        self.assertEqual(result, ["create_sort_style", "create_direct_iteration", "create_aggregation_style"])

    def test_every_iteration_preference_permutation_suppresses_conflict(self):
        names = ["직접 반복 사용", "인덱스 기반 반복 사용", "인덱싱 중심 구조"]
        for names_order in itertools.permutations(names):
            with self.subTest(names_order=names_order):
                self.assertFalse(set(actions(diff(missing_concept=names_order))) & {
                    "create_direct_iteration", "create_index_iteration"})


class CollectionAndDictionaryRegressionTests(unittest.TestCase):
    def test_safe_list_forward(self):
        self.assertEqual(actions(diff(missing_syntax=["리스트 컴프리헨션"])),
                         ["create_safe_comprehension_collection"])

    def test_safe_list_reverse(self):
        self.assertEqual(actions(diff(missing_concept=["리스트 누적 방식 사용"])),
                         ["create_safe_append_collection"])

    def test_both_list_preferences_fail_closed(self):
        self.assertEqual(actions(diff(missing_syntax=["리스트 컴프리헨션"],
                                      missing_concept=["리스트 누적 방식 사용"])), [])

    def test_list_conflict_does_not_remove_dictionary(self):
        self.assertEqual(actions(diff(missing_syntax=["리스트 컴프리헨션", "딕셔너리 컴프리헨션"],
                                      missing_concept=["리스트 누적 방식 사용"])),
                         ["create_safe_dict_comprehension"])

    def test_dict_forward(self):
        self.assertEqual(actions(diff(missing_syntax=["딕셔너리 컴프리헨션"])),
                         ["create_safe_dict_comprehension"])

    def test_dict_reverse(self):
        self.assertEqual(actions(diff(style_syntax=["for문", "딕셔너리 리터럴"],
                                      target_syntax=["딕셔너리 컴프리헨션"])),
                         ["create_safe_dict_loop"])

    def test_dict_no_reverse_without_saved_evidence(self):
        self.assertEqual(actions(diff(style_syntax=["for문"],
                                      target_syntax=["딕셔너리 컴프리헨션"])), [])

    def test_list_and_dict_forward_both_selected(self):
        self.assertEqual(actions(diff(missing_syntax=["리스트 컴프리헨션", "딕셔너리 컴프리헨션"])),
                         ["create_safe_dict_comprehension", "create_safe_comprehension_collection"])

    def test_iteration_conflict_does_not_remove_list_or_dict(self):
        result = actions(diff(missing_syntax=["리스트 컴프리헨션", "딕셔너리 컴프리헨션"],
                              missing_concept=["직접 반복 사용", "인덱스 기반 반복 사용"]))
        self.assertEqual(set(result), {"create_safe_dict_comprehension", "create_safe_comprehension_collection"})


class StylePlanAuditTests(unittest.TestCase):
    def test_report_contains_selected_action(self):
        report = audit_saved_style_plan(diff(missing_syntax=["딕셔너리 컴프리헨션"]))
        self.assertEqual([a["action"] for a in report["selected_actions"]],
                         ["create_safe_dict_comprehension"])

    def test_report_warns_iteration_conflict(self):
        report = audit_saved_style_plan(diff(missing_concept=["직접 반복 사용", "인덱스 기반 반복 사용"]))
        self.assertTrue(report["conflict_warnings"])
        self.assertFalse(report["has_actions"])

    def test_report_warns_list_conflict(self):
        report = audit_saved_style_plan(diff(missing_syntax=["리스트 컴프리헨션"],
                                             missing_concept=["리스트 누적 방식 사용"]))
        self.assertTrue(any("리스트" in s for s in report["conflict_warnings"]))

    def test_report_implemented_set_tag_is_linked(self):
        report = audit_saved_style_plan(diff(missing_syntax=["세트 컴프리헨션"]))
        self.assertNotIn("세트 컴프리헨션", report["compare_only"])
        self.assertIn("create_safe_set_comprehension", [
            a["action"] for a in report["selected_actions"]
        ])

    def test_empty_report(self):
        report = audit_saved_style_plan(diff())
        self.assertEqual(report["selected_actions"], [])
        self.assertFalse(report["has_actions"])

    def test_invalid_diff_rejected(self):
        with self.assertRaises(TypeError):
            audit_saved_style_plan(None)

    def test_report_does_not_mutate_diff(self):
        d = diff(missing_concept=["직접 반복 사용"])
        original = [dict(x) for x in d["missing_concept_tags"]]
        audit_saved_style_plan(d)
        self.assertEqual(d["missing_concept_tags"], original)

    def test_unrelated_tag_still_selected_during_conflict(self):
        report = audit_saved_style_plan(diff(missing_concept=["직접 반복 사용", "인덱스 기반 반복 사용", "정렬 중심 구조"]))
        self.assertEqual([a["action"] for a in report["selected_actions"]], ["create_sort_style"])
        self.assertEqual(len(report["conflict_warnings"]), 1)


if __name__ == "__main__":
    unittest.main()
