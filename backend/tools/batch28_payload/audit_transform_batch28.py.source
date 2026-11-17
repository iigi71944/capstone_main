"""Batch28 registry-policy audit; keeps prior 285 representative fixtures.

This batch refactors selection policy only, and does not claim 3 new examples
per tag. The Batch27 285 representative source transforms remain the same.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
for path in (BACKEND, BACKEND / 'tools', BACKEND / 'tests'):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import audit_transform_batch27 as previous
from app.services.style_tag_action_policy_service import (
    SHARED_TAG_FAMILIES, TAG_ACTION_POLICIES,
    get_tag_action_policy, finalize_tag_action_policies,
)
from app.services.style_tag_transform_map_service import CREATE_ACTION_BY_TAG
from app.services.style_apply_service import _get_transform_function


def audit() -> dict:
    report = previous.audit()
    issues = list(report['summary'].get('audit_issues', []))
    identities = set()
    for family, tags in SHARED_TAG_FAMILIES.items():
        if len(tags) != 2:
            issues.append(f'{family}: expected two tag policies')
            continue
        actions = []
        for tag in tags:
            action = CREATE_ACTION_BY_TAG.get(tag)
            policy = get_tag_action_policy(tag, action)
            if action is None or policy is None or not callable(_get_transform_function(action)):
                issues.append(f'{tag}: missing registry, policy or dispatcher')
                continue
            identities.add(policy['policy_action'])
            actions.append({'tag':tag, 'action':action, 'reason':'audit'})
        if len(actions) == 2:
            merged = finalize_tag_action_policies(actions)
            if len(merged) != 1 or merged[0].get('policy_family') != family:
                issues.append(f'{family}: shared action not deduplicated')
            if set(merged[0].get('policy_source_tags', [])) != set(tags):
                issues.append(f'{family}: origin tags not recorded')
    if len(identities) != 32:
        issues.append(f'expected 32 distinct policies; got {len(identities)}')
    if len(TAG_ACTION_POLICIES) != 32:
        issues.append(f'expected 32 policies; got {len(TAG_ACTION_POLICIES)}')
    summary = report['summary']
    summary['batch28_shared_families'] = len(SHARED_TAG_FAMILIES)
    summary['batch28_distinct_tag_policies'] = len(TAG_ACTION_POLICIES)
    summary['batch28_policy_issues'] = issues
    # Keep the legacy summary status truthful: Batch28 added no new tag links.
    summary['audit_issues'] = issues
    report['batch28_note'] = (
        'Existing 95 tag links and 285 representative transformations retained. '
        '32 independent tag-policy identifiers in 16 duplicate families now '
        'deduplicate compatible actions; shared low-level engines are intentional. '
        'No frontend files or saved-style JSON fields were changed.'
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    result = audit()
    summary = result['summary']
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print('=== 28차 태그별 변환 정책 중복 감사 ===')
        print(f"전체 {summary['tags']} / 연결 {summary['linked']} / 비교전용 {summary['compare_only']}")
        print(f"공유 그룹 {summary['batch28_shared_families']} / 독립 태그 정책 {summary['batch28_distinct_tag_policies']}")
        print(f"기존 3종 대표 검사 {summary['representative_tests_passed']}/{summary['representative_tests']} 통과")
        for issue in summary['audit_issues']:
            print('감사 문제:', issue)
    return 0 if (
        summary['tags'] == 102 and summary['linked'] == 95
        and summary['compare_only'] == 7
        and summary['batch28_shared_families'] == 16
        and summary['batch28_distinct_tag_policies'] == 32
        and summary['registry_status'] == 'ok'
        and not summary['registry_issues']
        and not summary['audit_issues']
        and summary['representative_tests'] == 285
        and summary['representative_tests_passed'] == 285
    ) else 1


if __name__ == '__main__':
    raise SystemExit(main())
