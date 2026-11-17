"""Batch36-4: compare the same 50 fixtures and independently test composition.

This benchmark is intentionally deterministic and synthetic, not an external
Python corpus or a universal proof of behavioral equivalence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from tools.audit_batch36_1 import run_audit
from tools.batch36_1_cases import CASES

REPORT_VERSION = 1


def validate_baseline(base: dict) -> dict:
    if not isinstance(base, dict) or base.get('report_version') != 1:
        raise ValueError('36-3 보고서 버전이 다릅니다.')
    current = base.get('current')
    if not isinstance(current, dict) or any(type(current.get(k)) is not int for k in
        ('changed', 'verified_changes', 'no_safe_pattern', 'preflight_skipped')):
        raise ValueError('36-3 보고서 current 집계가 필요합니다.')
    if current['changed'] > 50 or current['verified_changes'] > current['changed']:
        raise ValueError('36-3 집계 범위가 유효하지 않습니다.')
    if base.get('contract', {}).get('action_ledger_consistent') is not True:
        raise ValueError('36-3 액션 추적 일관성이 검증되지 않았습니다.')
    return current


def make_report(base: dict, normal: dict, strict: dict) -> dict:
    previous = validate_baseline(base)
    if (normal.get('case_count') != 50 or strict.get('case_count') != 50
        or [c.get('id') for c in normal.get('cases', [])]
        != [case.case_id for case in CASES]):
        raise ValueError('기존 50개 사례 전체의 동일 ID 비교가 필요합니다.')
    summary = normal['summary']
    strict_summary = strict['summary']
    r45 = next(row for row in normal['cases'] if row['id'] == 'R45')
    strict_r45 = next(row for row in strict['cases'] if row['id'] == 'R45')
    unsafe = [r['id'] for r in strict['cases'] if r['changed'] and
        not (r['verification_status'] == 'equivalent' and r.get('verification_equivalent') is True)]
    old_cases = {row['id']: row for row in base.get('cases', []) if isinstance(row, dict) and 'id' in row}
    tag_targets = {'lambda식', '리스트 컴프리헨션', '컴프리헨션 기반 간결 구조'}
    r45_resolved = set(r45.get('resolved_tags') or [])
    report = {
        'report_version': REPORT_VERSION,
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': '50 authored cases; exact 36-3 baseline comparison; closed pure-helper composition',
        'baseline': {k: previous[k] for k in ('changed', 'verified_changes', 'no_safe_pattern', 'preflight_skipped')},
        'current': {
            'changed': summary['changed_cases'],
            'verified_changes': summary['changed_and_runtime_equivalent'],
            'no_safe_pattern': summary['attempt_status_counts'].get('no_safe_pattern', 0),
            'preflight_skipped': summary['attempt_status_counts'].get('skipped_shape_preflight', 0),
            'resolved_tags': summary['resolved_missing_tag_instances'],
            'introduced_tags': summary['newly_missing_tag_instances'],
            'failed_cases': summary['failed_case_ids'],
        },
        'strict': {
            'changed': strict_summary['changed_cases'],
            'verified_changes': strict_summary['changed_and_runtime_equivalent'],
            'unverified_changed_cases': unsafe,
            'failed_cases': strict_summary['failed_case_ids'],
        },
        'deltas': {
            'changed': summary['changed_cases'] - previous['changed'],
            'verified_changes': summary['changed_and_runtime_equivalent'] - previous['verified_changes'],
            'no_safe_pattern': summary['attempt_status_counts'].get('no_safe_pattern', 0) - previous['no_safe_pattern'],
        },
        'composite_R45': {
            'changed': r45['changed'],
            'verification_status': r45['verification_status'],
            'verification_equivalent': r45.get('verification_equivalent'),
            'initial_missing_tags': r45.get('initial_missing_tags', []),
            'resolved_tags': r45.get('resolved_tags', []),
            'remaining_tags': r45.get('final_missing_tags', []),
            'core_composite_tags_resolved': sorted(tag_targets & r45_resolved),
            'strict_changed': strict_r45['changed'],
            'strict_verification_status': strict_r45['verification_status'],
            'diff_excerpt': r45.get('diff_excerpt', ''),
        },
        'contract': {
            'strict_unverified_changed_cases': unsafe,
            'normal_failed_case_ids': summary['failed_case_ids'],
            'strict_failed_case_ids': strict_summary['failed_case_ids'],
            'same_50_ids': True,
        },
    }
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description='Batch36-4 composite style audit')
    parser.add_argument('--baseline', default='batch36_3_audit.json')
    parser.add_argument('--output', default='batch36_4_audit.json')
    args = parser.parse_args(argv)
    try:
        baseline = json.loads(Path(args.baseline).read_text(encoding='utf-8'))
        validate_baseline(baseline)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        parser.error(f'36-3 기준 보고서 오류: {exc}')
    normal = run_audit(CASES, strict_runtime_validation=False)
    strict = run_audit(CASES, strict_runtime_validation=True)
    report = make_report(baseline, normal, strict)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('=== Batch36-4 복합 스타일 / 동일 50개 재평가 ===')
    print('코드 변경:', report['baseline']['changed'], '→', report['current']['changed'])
    print('실행 동등성 확인:', report['baseline']['verified_changes'], '→', report['current']['verified_changes'])
    print('no_safe_pattern:', report['baseline']['no_safe_pattern'], '→', report['current']['no_safe_pattern'])
    print('R45 복합 태그 해소:', report['composite_R45']['core_composite_tags_resolved'])
    print('R45 변환 및 검증:', report['composite_R45']['changed'], report['composite_R45']['verification_status'])
    print('엄격 모드 미검증 변경:', report['strict']['unverified_changed_cases'])
    print('보고서:', out)
    invalid = (report['strict']['unverified_changed_cases']
               or report['current']['failed_cases']
               or report['strict']['failed_cases']
               or not report['composite_R45']['changed']
               or report['composite_R45']['verification_status'] != 'equivalent'
               or not {'lambda식', '리스트 컴프리헨션'} <=
               set(report['composite_R45']['core_composite_tags_resolved']))
    return 1 if invalid else 0


if __name__ == '__main__':
    raise SystemExit(main())
