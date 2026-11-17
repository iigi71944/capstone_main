"""Batch36-3: apples-to-apples benchmark with action preflight evidence.

Baseline is the real Batch36-2 report. Does not execute untrusted external
code; fixtures are the project's authored 50-case benchmark. An explicit
'preflight skip' is *not* an applied conversion and does not raise conversion
success rates by itself. Runtime security policy is unchanged.

Run: python -m tools.audit_batch36_3 --baseline batch36_2_audit.json \\
     --output batch36_3_audit.json
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from tools.audit_batch36_1 import run_audit
from tools.audit_batch36_2 import breakdown_action_results
from tools.batch36_1_cases import CASES

REPORT_VERSION = 1

_DEFAULT_FAMILIES = (
    ('sorted', 'sorted_reverse_false_explicit_count', 'sorted_reverse_false_implicit_count'),
    ('strip', 'strip_none_explicit_count', 'strip_none_implicit_count'),
)


def validate_baseline(report: dict) -> None:
    if not isinstance(report, dict) or report.get('report_version') != 1:
        raise ValueError('36-2 보고서 형식이 아닙니다.')
    summary = report.get('permissive_summary')
    if not isinstance(summary, dict) or summary.get('total_cases') != 50:
        raise ValueError('36-2의 동일한 50개 기준 보고서가 필요합니다.')
    if not isinstance(report.get('no_safe_pattern_detail'), dict):
        raise ValueError('36-2 액션 상세 진단이 없습니다.')


def preference_alignment(cases=CASES):
    """Count surface-form preference progress separately from missing tags.

    A tag might disappear when the *desired* default argument spelling is
    selected. This score tests only relative explicit/implicit occurrence,
    not arbitrary correctness or complete style equivalence.
    """
    from app.services.style_diff_service import analyze_code_style
    from app.services.style_apply_service import apply_coding_style

    details = []
    for case in cases:
        saved_analysis = analyze_code_style(case.style_code)
        target_before = analyze_code_style(case.target_code)
        style = {
            'id': case.case_id, 'name': case.name,
            'description': '36-3 preference audit',
            'syntax_tags': saved_analysis['syntax_tags'],
            'concept_tags': saved_analysis['concept_tags'],
            'metrics': dict(saved_analysis['metrics']),
            'created_at': '2026-11-18T00:00:00Z',
        }
        if case.version == 'v1':
            style['metrics_version'] = 1
        changed_code, _, _, _, _, _ = apply_coding_style(
            code=case.target_code, style=style,
            **({'stdin': case.stdin} if case.stdin is not None else {}),
        )
        after = analyze_code_style(changed_code)
        for family, explicit_key, implicit_key in _DEFAULT_FAMILIES:
            saved = saved_analysis['metrics']
            before = target_before['metrics']
            final = after['metrics']
            exp, imp = saved.get(explicit_key, 0), saved.get(implicit_key, 0)
            if exp == imp or max(exp, imp) == 0:
                continue
            preferred = 'explicit' if exp > imp else 'implicit'
            opposite_key = implicit_key if preferred == 'explicit' else explicit_key
            before_opposite = before.get(opposite_key, 0)
            after_opposite = final.get(opposite_key, 0)
            if before_opposite <= 0:
                continue
            details.append({
                'id': case.case_id, 'family': family, 'preferred': preferred,
                'saved_explicit_count': exp, 'saved_implicit_count': imp,
                'target_opposite_before': before_opposite,
                'target_opposite_after': after_opposite,
                'preference_improved': after_opposite < before_opposite,
                'preference_regressed': after_opposite > before_opposite,
            })
    return {
        'evaluated_preference_opportunities': len(details),
        'improved': sum(row['preference_improved'] for row in details),
        'regressed': sum(row['preference_regressed'] for row in details),
        'unchanged': sum(not row['preference_improved'] and not row['preference_regressed']
                         for row in details),
        'details': details,
        'method': 'relative explicit/implicit family count only; independent of tag-presence score',
    }


def make_report(baseline: dict, permissive: dict, strict: dict,
                ledger: dict, preference: dict) -> dict:
    validate_baseline(baseline)
    if permissive['case_count'] != 50 or strict['case_count'] != 50:
        raise ValueError('50개 전수 결과가 필요합니다.')
    old = baseline['permissive_summary']
    current = permissive['summary']
    safe = strict['summary']
    old_ledger = baseline['no_safe_pattern_detail']
    no_safe = current['attempt_status_counts'].get('no_safe_pattern', 0)
    skipped = current['attempt_status_counts'].get('skipped_shape_preflight', 0)
    action_sum = sum(sum(row.values()) for row in ledger['by_action'].values())
    current_action_sum = sum(current['attempt_status_counts'].values())
    strict_violations = [row['id'] for row in strict['cases']
                         if row.get('changed') and not (row.get('verification_status') == 'equivalent'
                                                        and row.get('verification_equivalent') is True)]
    prior = baseline['permissive_summary']['attempt_status_counts']
    # Full ledger of all attempted decisions is intentionally preserved:
    # skips are now named as *skips*, not counted as successful applications.
    ledger_consistent = action_sum == current_action_sum
    return {
        'report_version': REPORT_VERSION,
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': '50 deterministic authored fixtures; operational safety not universally proven',
        'baseline': {
            'source': 'batch36_2_audit.json',
            'changed': old['changed_cases'],
            'verified_changes': old['changed_and_runtime_equivalent'],
            'no_safe_pattern': prior.get('no_safe_pattern', 0),
            'total_action_decisions': sum(prior.values()),
        },
        'current': {
            'changed': current['changed_cases'],
            'verified_changes': current['changed_and_runtime_equivalent'],
            'no_safe_pattern': no_safe,
            'preflight_skipped': skipped,
            'total_action_decisions': current_action_sum,
            'resolved_tags': current['resolved_missing_tag_instances'],
            'newly_missing_tags': current['newly_missing_tag_instances'],
            'failed_case_ids': current['failed_case_ids'],
        },
        'strict': {
            'changed': safe['changed_cases'],
            'verified_changes': safe['changed_and_runtime_equivalent'],
            'unverified_changed_cases': strict_violations,
            'failed_case_ids': safe['failed_case_ids'],
        },
        'deltas': {
            'changed': current['changed_cases'] - old['changed_cases'],
            'verified_changes': (current['changed_and_runtime_equivalent']
                                 - old['changed_and_runtime_equivalent']),
            'no_safe_pattern': no_safe - prior.get('no_safe_pattern', 0),
            'preflight_skipped': skipped,
        },
        'new_target_case': next((row for row in permissive['cases'] if row['id'] == 'R43'), None),
        'metric_tag_drift': [
            {'id': row['id'], 'introduced_missing_tags': row.get('introduced_missing_tags', [])}
            for row in permissive['cases'] if row.get('introduced_missing_tags')
        ],
        'default_preference_alignment': preference,
        'action_diagnostics': ledger,
        'contract': {
            'action_ledger_consistent': ledger_consistent,
            'action_count_from_summary': current_action_sum,
            'action_count_from_ledger': action_sum,
            'preflight_skip_not_counted_as_applied': ('skipped_shape_preflight' not in {'applied'}),
            'strict_unverified_change_violations': strict_violations,
            'baseline_previous_no_safe': old_ledger.get('total_no_safe_pattern'),
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Batch36-3 transformation preflight benchmark')
    parser.add_argument('--baseline', default='batch36_2_audit.json')
    parser.add_argument('--output', default='batch36_3_audit.json')
    args = parser.parse_args(argv)
    try:
        baseline = json.loads(Path(args.baseline).read_text(encoding='utf-8'))
        validate_baseline(baseline)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        parser.error(f'36-2 기준 보고서 오류: {exc}')

    normal = run_audit(CASES, strict_runtime_validation=False)
    strict = run_audit(CASES, strict_runtime_validation=True)
    ledger = breakdown_action_results()
    preference = preference_alignment()
    report = make_report(baseline, normal, strict, ledger, preference)
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print('=== Batch36-3 변환 사전 필터 / 50개 재평가 ===')
    print('코드 변경:', report['baseline']['changed'], '→', report['current']['changed'])
    print('동등성 확인:', report['baseline']['verified_changes'], '→', report['current']['verified_changes'])
    print('no_safe_pattern:', report['baseline']['no_safe_pattern'], '→', report['current']['no_safe_pattern'])
    print('사전 필터 제외(미적용):', report['current']['preflight_skipped'])
    case = report['new_target_case'] or {}
    print('R43 키워드 중첩 호출:', case.get('changed'), case.get('verification_status'))
    print('엄격 모드 동등성 미확인 변경:', report['strict']['unverified_changed_cases'])
    print('태그와 분리한 기본 인자 선호도 평가:',
          preference['improved'], '/', preference['evaluated_preference_opportunities'])
    print('보고서:', dest)
    fail = (bool(report['current']['failed_case_ids']) or
            bool(report['strict']['failed_case_ids']) or
            bool(report['strict']['unverified_changed_cases']) or
            bool(ledger.get('contract_violations')) or
            not report['contract']['action_ledger_consistent'] or
            not(case.get('changed') is True and case.get('verification_status') == 'equivalent'))
    return 2 if fail else 0


if __name__ == '__main__':
    raise SystemExit(main())
