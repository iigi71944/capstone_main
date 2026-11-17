"""33차: 32차 변환 관측 누락 6태그의 대표 테스트 호출 경로 분리 감사.

IMPORTANT: legacy public actions and safe transformers are distinct functions.
This audit does not silently treat a passing safe-transformer test as proof
that the public production action or whole saved-style pipeline applied it.
Only repository-shipped trusted unittest fixtures run. No user source input.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
for root in (BACKEND, BACKEND / 'tools', BACKEND / 'tests'):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

import audit_transform_batch32 as prior
from app.services.style_apply_service import _get_transform_function
from app.services.improvement.safe_index_iteration_service import (
    transform_to_direct_iteration_style as safe_direct_iteration,
    transform_to_index_iteration_style as safe_index_iteration,
)
from app.services.improvement.safe_list_comprehension_service import (
    transform_for_append_to_list_comprehension as safe_list_collapse,
    transform_list_comprehension_to_for_append as safe_list_expand,
)
from app.services.improvement.safe_dict_comprehension_service import (
    transform_for_assignment_to_dict_comprehension as safe_dict_collapse,
)

# Each entry is (real fixture transformer, optional available dispatcher action).
# Do not guess that the public legacy action is the same as these tested helpers.
MISSED_FIXTURES = {
    '딕셔너리 컴프리헨션': (safe_dict_collapse, 'create_safe_dict_comprehension'),
    '리스트 누적 방식 사용': (safe_list_expand, 'create_safe_append_collection'),
    '리스트 컴프리헨션': (safe_list_collapse, 'create_safe_comprehension_collection'),
    '인덱스 기반 반복 사용': (safe_index_iteration, None),
    '인덱싱 중심 구조': (safe_index_iteration, None),
    '직접 반복 사용': (safe_direct_iteration, None),
}
LEVELS = ('basic', 'additional', 'complex')


def _status_on_sample(tag: str, action: str | None, source: str) -> str:
    if not action:
        return 'not_registered'
    return prior.check_apply_action(tag, action, source)


def audit() -> dict:
    baseline = prior.audit()
    s = baseline['summary']
    issues = list(baseline['issues'])
    by_tag = {item['tag']: item for item in baseline['tags']}
    details = []
    safe_passed = safe_edited = public_applied = safe_routed = 0

    for tag, (transformer, safe_action) in MISSED_FIXTURES.items():
        original = by_tag.get(tag)
        if original is None:
            issues.append(f'{tag}: 32차 기준 감사에서 태그를 찾지 못했습니다.')
            continue
        action = original['action']
        first_source = None
        case_results = []
        if len(original['cases']) != 3:
            issues.append(f'{tag}: 대표 사례 개수가 3개가 아닙니다.')
        for case in original['cases']:
            ok, message, trace = prior.trace_representative_case(case['test'], transformer)
            valid_edit = ok and trace.changed > 0 and trace.invalid == 0 and trace.sample is not None
            safe_passed += int(ok)
            safe_edited += int(valid_edit)
            if first_source is None and valid_edit:
                first_source = trace.sample[0]
            if not ok or not valid_edit:
                issues.append(f"{tag} / {case['test']}: 안전형 호출·실제 변경 근거 부족; {message[-250:]}")
            case_results.append({
                'level': case['level'], 'test': case['test'],
                'passed': ok, 'safe_transformer_calls': trace.calls,
                'safe_edits': trace.changed, 'safe_invalid_python': trace.invalid,
                'safe_edit_observed': valid_edit,
            })
        safe_dispatch = (_get_transform_function(safe_action)
                         if safe_action is not None else None)
        routed = safe_dispatch is transformer
        if safe_action and not routed:
            issues.append(f'{tag}: 안전형 액션 {safe_action}이 대표 테스트 함수와 연결되지 않았습니다.')
        safe_routed += int(routed)
        if first_source is None:
            public_status = 'no_fixture_source'
            safe_status = 'no_fixture_source'
        else:
            public_status = _status_on_sample(tag, action, first_source)
            safe_status = (_status_on_sample(tag, safe_action, first_source)
                           if routed else 'not_registered')
        public_applied += int(public_status == 'applied')
        details.append({
            'tag': tag,
            'public_action': action,
            'safe_tested_transformer': transformer.__name__,
            'safe_dispatch_action': safe_action,
            'safe_transformer_in_dispatcher': routed,
            'public_action_on_safe_fixture': public_status,
            'safe_action_on_safe_fixture': safe_status,
            'cases': case_results,
        })

    original_tag_count = int(s.get('tags_with_observed_edit', 0))
    # The additional six have tests of DIFFERENT functions. This is a
    # heterogeneous evidence count, not a new "production success rate".
    covered_tags = set(row['tag'] for row in baseline['tags'] if row['observed_edit'])
    for entry in details:
        if len(entry['cases']) == 3 and all(c['safe_edit_observed'] for c in entry['cases']):
            covered_tags.add(entry['tag'])
    summary = {
        'tags': s.get('tags'),
        'linked': s.get('linked'),
        'baseline_public_action_observed_tags': original_tag_count,
        'baseline_public_action_observed_cases': s.get('edited_cases'),
        'baseline_case_count': s.get('replayed_cases'),
        'legacy_public_action_unobserved_tags': s.get('tags_without_observed_edit'),
        'alternate_safe_fixture_cases': len(MISSED_FIXTURES) * 3,
        'alternate_safe_fixture_tests_passed': safe_passed,
        'alternate_safe_fixture_edits': safe_edited,
        'alternate_safe_fixture_tags': sum(
            len(item['cases']) == 3 and all(c['safe_edit_observed'] for c in item['cases'])
            for item in details
        ),
        'either_tested_transformer_observed_tags': len(covered_tags),
        'safe_transformers_with_registered_action': safe_routed,
        'public_action_applied_on_safe_fixture_tags': public_applied,
        'issues': len(issues),
    }
    return {
        'summary': summary,
        'six_tag_details': details,
        'issues': issues,
        'methodology': {
            'legacy_public': '32차는 각 태그 공개 액션 함수만 추적했습니다.',
            'alternate': '33차는 해당 6태그의 대표 테스트가 실제로 호출하는 별도 안전형 함수를 관측했습니다.',
            'warning': '두 근거를 합친 태그 수는 공개 액션 적용 성공률 또는 임의 Python 코드의 성공률이 아닙니다.',
            'public_probe': '공개 액션을 대표 안전형 입력에 직접 적용해 변경 여부만 확인합니다. 동등성 증명 아님.',
            'runtime': '실행 동등성은 여기서 별도로 검증하지 않습니다. 기존 테스트에 있는 관찰 실행만 수행됩니다.',
            'limitations': '인덱스 관련 3태그의 독립 안전형 함수는 공개 디스패처 액션과 별개입니다.',
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = audit()
    s = report['summary']
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print('=== 33차 감사 대상 함수 일치·실제 코드 변경 교차 검사 ===')
        print(f"태그 연결 {s['linked']}/{s['tags']}")
        print(f"기존 공개 액션 추적: 태그 {s['baseline_public_action_observed_tags']}/{s['tags']}, 사례 {s['baseline_public_action_observed_cases']}/{s['baseline_case_count']}")
        print(f"누락 6태그 안전형 테스트 재실행 {s['alternate_safe_fixture_tests_passed']}/{s['alternate_safe_fixture_cases']}")
        print(f"안전형 실제 코드 변경 {s['alternate_safe_fixture_edits']}/{s['alternate_safe_fixture_cases']}")
        print(f"대표 테스트의 공개+안전형 근거를 합친 변경 관측 태그 {s['either_tested_transformer_observed_tags']}/{s['tags']}")
        print(f"안전형 함수 디스패처 연결 {s['safe_transformers_with_registered_action']}/6")
        print(f"공개 액션이 안전형 입력에 직접 적용된 태그 {s['public_action_applied_on_safe_fixture_tags']}/6")
        print('주의: 안전형 변환 테스트 성공은 공개 액션의 실제 적용 성공을 보장하지 않습니다.')
        for row in report['six_tag_details']:
            print(f"- {row['tag']}: 공개={row['public_action_on_safe_fixture']}, 안전형={row['safe_action_on_safe_fixture']}")
        print(f"감사 오류 {s['issues']}건")
        for issue in report['issues'][:8]:
            print('검증 오류:', issue)
        if not args.output:
            print('상세 보고서: --output backend/batch33_audit.json (선택)')
    return 0 if (
        s['issues'] == 0 and s['linked'] == s['tags'] == 102
        and s['baseline_case_count'] == 306
        and s['alternate_safe_fixture_cases'] == s['alternate_safe_fixture_tests_passed'] == s['alternate_safe_fixture_edits'] == 18
        and s['alternate_safe_fixture_tags'] == 6
        and s['either_tested_transformer_observed_tags'] == 102
        and s['safe_transformers_with_registered_action'] == 3
    ) else 1


if __name__ == '__main__':
    raise SystemExit(main())
