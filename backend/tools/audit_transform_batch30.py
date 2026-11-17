"""30차: 16개 공유 태그 가족 정책 + 29차 세부 양방향 충돌 감사.

Legacy representative triplets are retained. Extra checks are deliberately
restricted to documented fixtures, NOT a universal semantics proof.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
for p in (BACKEND, BACKEND / 'tools', BACKEND / 'tests'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import audit_transform_batch29 as prior
import audit_transform_three_patterns as base
from app.services.style_tag_action_policy_service import (
    SHARED_TAG_FAMILIES, TAG_ACTION_POLICIES,
)
from app.services.style_tag_transform_map_service import (
    CREATE_ACTION_BY_TAG, COMPARE_ONLY_TAGS,
)


LEVELS = ('basic', 'additional', 'complex')
FINE_DIRECTIONS = ('sorted_explicit', 'sorted_implicit',
                   'strip_explicit', 'strip_implicit')
CONFLICT_IDS = tuple(f'test_{i:02d}_{name}' for i, name in (
    (1, 'tag_count_and_29_metric_schema'),
    (2, 'old_missing_metric_is_noop'),
    (3, 'mixed_saved_sorted_style_is_not_guessed'),
    (4, 'mixed_saved_strip_style_is_not_guessed'),
    (5, 'opposite_sorted_directions_conflict'),
    (6, 'opposite_strip_directions_conflict'),
    (7, 'sort_and_strip_coexist_without_cross_family_suppression'),
    (8, 'real_code_both_fine_actions_preserve_output'),
    (9, 'mismatched_method_receiver_is_not_rewritten'),
    (10, 'dynamic_sorted_parameter_is_not_rewritten'),
    (11, 'unknown_reverse_action_is_preserved'),
    (12, 'public_registry_and_saved_tag_names_are_unchanged'),
))


def audit():
    report = prior.audit()
    summary = report['summary']
    problems = list(summary.get('audit_issues', []))
    cases = []

    if len(SHARED_TAG_FAMILIES) != 16 or len(TAG_ACTION_POLICIES) != 32:
        problems.append('정책 가족 개수 불일치: 16그룹/32태그 정책이 필요합니다.')
    if (len(CREATE_ACTION_BY_TAG) < 95 or len(COMPARE_ONLY_TAGS) > 7
            or len(CREATE_ACTION_BY_TAG) + len(COMPARE_ONLY_TAGS) != 102):
        problems.append('기존 태그 등록 개수가 변경됐습니다.')

    for family in SHARED_TAG_FAMILIES:
        for level in LEVELS:
            cases.append(('shared', family, level,
                          f'test_style_batch30_policy_conflicts.SharedTagPolicyTriplets.test_{family}_{level}'))
    for variant in FINE_DIRECTIONS:
        for level in LEVELS:
            cases.append(('fine', variant, level,
                          f'test_style_batch30_policy_conflicts.FineDirectionTriplets.test_{variant}_{level}'))
    for test_name in CONFLICT_IDS:
        cases.append(('conflict', test_name, 'single',
                      f'test_style_batch30_policy_conflicts.ConflictCompatibilityTests.{test_name}'))

    results = []
    for kind, name, level, test_id in cases:
        ok, detail = base._run_case(test_id)
        result = {'group': kind, 'name': name, 'level': level,
                  'test': test_id, 'passed': ok}
        if not ok:
            result['error'] = detail
            problems.append(f'{test_id}: {detail}')
        results.append(result)

    counted = {kind: [r for r in results if r['group'] == kind]
               for kind in ('shared', 'fine', 'conflict')}
    report['batch30'] = {
        'policy_cases': counted['shared'],
        'fine_cases': counted['fine'],
        'conflict_cases': counted['conflict'],
    }
    for kind, rows in counted.items():
        summary[f'batch30_{kind}_total'] = len(rows)
        summary[f'batch30_{kind}_passed'] = sum(bool(r['passed']) for r in rows)
    summary['batch30_total'] = len(results)
    summary['batch30_passed'] = sum(bool(r['passed']) for r in results)
    summary['batch30_shared_families'] = len(SHARED_TAG_FAMILIES)
    summary['batch30_independent_tag_policies'] = len(TAG_ACTION_POLICIES)
    summary['audit_issues'] = problems
    report['batch30_notes'] = (
        'The original 285 representative cases and 29th granular 12 cases are '
        'preserved. 30th tests check policy decisions, explicit-default edits '
        'and conflict guards without modifying frontend or transformers.'
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    report = audit()
    s = report['summary']
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print('=== 30차 태그별 3종 정책·세부 변환 충돌 감사 ===')
        print(f"전체 {s['tags']} / 연결 {s['linked']} / 비교전용 {s['compare_only']}")
        print(f"기존 대표 검사 {s['representative_tests_passed']}/{s['representative_tests']}")
        print(f"29차 세부 대표 검사 {s['batch29_granular_passed']}/{s['batch29_granular_tests']}")
        print(f"공유 태그 정책 3종 {s['batch30_shared_passed']}/{s['batch30_shared_total']}")
        print(f"세부 양방향 변환 3종 {s['batch30_fine_passed']}/{s['batch30_fine_total']}")
        print(f"기존 변환 충돌/호환성 {s['batch30_conflict_passed']}/{s['batch30_conflict_total']}")
        for issue in s['audit_issues']:
            print('감사 실패:', issue)
    return 0 if (
        not s['audit_issues'] and not s['registry_issues']
        and s['tags'] == 102 and s['linked'] >= 95 and s['compare_only'] <= 7
        and s['representative_tests_passed'] == s['representative_tests'] == 285
        and s['batch29_granular_passed'] == s['batch29_granular_tests'] == 12
        and s['batch30_shared_passed'] == s['batch30_shared_total'] == 48
        and s['batch30_fine_passed'] == s['batch30_fine_total'] == 12
        and s['batch30_conflict_passed'] == s['batch30_conflict_total'] == 12
        and s['batch30_total'] == 72 and s['batch30_passed'] == 72
        and s['batch30_shared_families'] == 16
        and s['batch30_independent_tag_policies'] == 32
    ) else 1


if __name__ == '__main__':
    raise SystemExit(main())
