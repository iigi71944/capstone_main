"""29차: retain the historical 285 triplets and check four granular directions."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
for path in (BACKEND, BACKEND / 'tools', BACKEND / 'tests'):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import audit_transform_batch28 as prior
import audit_transform_three_patterns as base
from app.services.style_apply_service import _get_transform_function

NEW = {
    'sorted_reverse_explicit': ('SortedExplicitTriplets', 'create_safe_explicit_sorted_reverse'),
    'sorted_reverse_implicit': ('SortedImplicitTriplets', 'create_safe_implicit_sorted_reverse'),
    'strip_none_explicit': ('StripExplicitTriplets', 'create_safe_explicit_strip_default'),
    'strip_none_implicit': ('StripImplicitTriplets', 'create_safe_implicit_strip_default'),
}


def audit():
    report = prior.audit()
    problems = list(report['summary'].get('audit_issues', []))
    passed = 0
    total = 0
    detail = []
    for variant, (cls, action) in NEW.items():
        if not callable(_get_transform_function(action)):
            problems.append(f'{variant}: missing action dispatcher')
            continue
        for level in ('basic', 'additional', 'complex'):
            test_id = f'test_style_batch29_fine_patterns.{cls}.test_{level}'
            ok, message = base._run_case(test_id)
            total += 1
            passed += int(ok)
            detail.append({'variant': variant, 'level': level, 'passed': ok})
            if not ok:
                problems.append(f'{test_id}: {message}')
    report['batch29'] = {'granular_cases': detail, 'passed': passed, 'total': total}
    report['summary']['batch29_granular_tests'] = total
    report['summary']['batch29_granular_passed'] = passed
    report['summary']['audit_issues'] = problems
    return report


def main():
    parser = argparse.ArgumentParser()
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
        print('=== 29차 세부 패턴 저장·적용 감사 ===')
        print(f"전체 {s['tags']} / 연결 {s['linked']} / 비교전용 {s['compare_only']}")
        print(f"기존 대표 검사 {s['representative_tests_passed']}/{s['representative_tests']}")
        print(f"세부 스타일 양방향 3종 검사 {s['batch29_granular_passed']}/{s['batch29_granular_tests']}")
        for error in s['audit_issues']:
            print('검증 문제:', error)
    return 0 if (not s['audit_issues'] and not s['registry_issues']
                 and s['tags'] == 102 and s['linked'] == 95
                 and s['compare_only'] == 7
                 and s['representative_tests_passed'] == 285
                 and s['representative_tests'] == 285
                 and s['batch29_granular_tests'] == 12
                 and s['batch29_granular_passed'] == 12) else 1


if __name__ == '__main__':
    raise SystemExit(main())
