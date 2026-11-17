"""Batch36-2: compare the 50-case legacy audit with repaired + strict results.

This tool is observational. Only the existing production service is invoked.
It DOES NOT execute a previously rejected asyncio script by weakening guards.
Run as: python -m tools.audit_batch36_2 --baseline batch36_1_audit.json \\
        --output batch36_2_audit.json
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from tools.audit_batch36_1 import evaluate_case, run_audit
from tools.batch36_1_cases import CASES

REPORT_VERSION = 1
STRIP_CASES = ('R13', 'R14', 'R18', 'R19')
ASYNC_CASES = ('R04', 'R05', 'R06')


def validate_baseline(baseline: dict, cases=CASES) -> dict[str, dict]:
    if not isinstance(baseline, dict) or baseline.get('report_version') != 1:
        raise ValueError('36-1 버전 1 보고서만 비교할 수 있습니다.')
    rows = baseline.get('cases')
    expected = [c.case_id for c in cases]
    if not isinstance(rows, list) or [r.get('id') if isinstance(r, dict) else None for r in rows] != expected:
        raise ValueError('36-1 보고서의 사례 ID/개수/순서가 현재 50개 예제와 다릅니다.')
    return {r['id']: r for r in rows}


def classify_unchanged(row: dict) -> str:
    """Do not treat deliberate safety skips as broken transformations."""
    if row.get('changed'):
        return 'changed'
    if row.get('initial_missing_count', 0) == 0:
        return 'already_no_missing_tag'
    if row.get('id') in {'R08', 'R09', 'R10'}:
        return 'intentional_negative_shape'
    if row.get('id') == 'R20':
        return 'insufficient_preference_evidence'
    return 'unresolved_safe_pattern_or_style_gap'


def breakdown_action_results(cases=CASES) -> dict:
    """Use the actual 35-3 per-action ledger, not a guessed warning count.

    One independent permissive pass is made for diagnostic evidence. It can be
    slower than the 36-1 summary, but does not alter stored styles or sources.
    """
    from app.services.style_diff_service import analyze_code_style
    from app.services.style_apply_service import apply_coding_style

    by_action: dict[str, Counter] = defaultdict(Counter)
    by_tag: dict[str, Counter] = defaultdict(Counter)
    reason_codes = Counter()
    violations = []
    for case in cases:
        analysis = analyze_code_style(case.style_code)
        style = {
            'id': case.case_id, 'name': case.name, 'description': 'Batch36-2 diagnostic',
            'syntax_tags': analysis['syntax_tags'],
            'concept_tags': analysis['concept_tags'],
            'metrics': dict(analysis['metrics']),
            'created_at': '2026-11-17T00:00:00Z',
        }
        if case.version == 'v1':
            style['metrics_version'] = 1
        response = apply_coding_style(
            code=case.target_code, style=style,
            **({'stdin': case.stdin} if case.stdin is not None else {}),
        )
        if len(response) != 6 or not isinstance(response[4], dict):
            violations.append(case.case_id + ': invalid application contract')
            continue
        diagnostic = response[4].get('transform_diagnostics', {})
        attempted = diagnostic.get('attempted_actions', []) if isinstance(diagnostic, dict) else []
        for item in attempted:
            if not isinstance(item, dict):
                continue
            status = item.get('status', 'unknown')
            action = item.get('action', '(unknown)')
            tag = item.get('tag', '(unknown)')
            if not isinstance(action, str):
                action = '(unknown)'
            if not isinstance(tag, str):
                tag = '(unknown)'
            by_action[action][str(status)] += 1
            by_tag[tag][str(status)] += 1
            reason_codes[str(item.get('reason_code', '(none)'))] += 1
    total_no_safe = sum(x.get('no_safe_pattern', 0) for x in by_action.values())
    return {
        'total_no_safe_pattern': total_no_safe,
        'by_action': {name: dict(counter) for name, counter in sorted(by_action.items())},
        'top_no_safe_actions': [
            {'action': name, 'no_safe_pattern': counter['no_safe_pattern'],
             'applied': counter.get('applied', 0)}
            for name, counter in sorted(by_action.items(),
                                        key=lambda row: (-row[1].get('no_safe_pattern', 0), row[0]))
            if counter.get('no_safe_pattern', 0) > 0
        ][:15],
        'by_tag': {name: dict(counter) for name, counter in sorted(by_tag.items())},
        'reason_counts': dict(reason_codes),
        'contract_violations': violations,
    }


def compare_reports(baseline: dict, permissive: dict, strict: dict,
                    action_details: dict) -> dict:
    old_rows = validate_baseline(baseline)
    normal_rows = validate_baseline(permissive)
    strict_rows = validate_baseline(strict)
    old = baseline['summary']
    new = permissive['summary']
    protected = strict['summary']

    strip = []
    for case_id in STRIP_CASES:
        a, b = old_rows[case_id], normal_rows[case_id]
        strip.append({
            'id': case_id,
            'was_changed': a.get('changed'),
            'now_changed': b.get('changed'),
            'now_verified': b.get('verification_status') == 'equivalent'
                            and b.get('verification_equivalent') is True,
            'resolved_tags': b.get('resolved_tags', []),
            'diff_excerpt': b.get('diff_excerpt', ''),
        })
    async_cases = []
    for case_id in ASYNC_CASES:
        p, s = normal_rows[case_id], strict_rows[case_id]
        async_cases.append({
            'id': case_id,
            'permissive_status': p.get('verification_status'),
            'permissive_changed': p.get('changed'),
            'strict_status': s.get('verification_status'),
            'strict_changed': s.get('changed'),
            'strict_rollback_confirmed': (p.get('verification_status') == 'not_verified'
                                          and p.get('changed') is True
                                          and s.get('changed') is False),
            'strict_warnings': s.get('warnings', []),
        })
    unchanged_reasons = Counter(classify_unchanged(row) for row in permissive['cases']
                                if not row.get('changed'))
    strict_violations = [
        row['id'] for row in strict['cases']
        if row.get('changed') and not (
            row.get('verification_status') == 'equivalent'
            and row.get('verification_equivalent') is True)
    ]
    return {
        'report_version': REPORT_VERSION,
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_baseline': {
            'report_version': baseline['report_version'],
            'generated_at_utc': baseline.get('generated_at_utc'),
            'case_count': len(old_rows),
        },
        'scope': '50 synthetic curated cases; not a proof of equivalence or a real-world corpus',
        'security_policy': 'unchanged: asyncio remains blocked; strict mode rolls back unverified changes',
        'baseline_summary': old,
        'permissive_summary': new,
        'strict_summary': protected,
        'deltas': {
            'changed_cases': new['changed_cases'] - old['changed_cases'],
            'verified_changes': (new['changed_and_runtime_equivalent']
                                 - old['changed_and_runtime_equivalent']),
            'no_safe_pattern_attempts': (new['attempt_status_counts'].get('no_safe_pattern', 0)
                                         - old['attempt_status_counts'].get('no_safe_pattern', 0)),
            'resolved_tags': (new['resolved_missing_tag_instances']
                              - old['resolved_missing_tag_instances']),
            'introduced_tags': (new['newly_missing_tag_instances']
                                - old['newly_missing_tag_instances']),
        },
        'strip_cases': strip,
        'async_cases': async_cases,
        'unchanged_case_classification': dict(unchanged_reasons),
        'metric_tag_drift': [
            {'id': row['id'], 'introduced_missing_tags': row.get('introduced_missing_tags', [])}
            for row in permissive['cases'] if row.get('introduced_missing_tags')
        ],
        'no_safe_pattern_detail': action_details,
        'strict_unverified_change_violations': strict_violations,
        'failed_cases': {
            'permissive': new.get('failed_case_ids', []),
            'strict': protected.get('failed_case_ids', []),
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Batch36-2: 36-1 before/after + strict audit')
    parser.add_argument('--baseline', default='batch36_1_audit.json')
    parser.add_argument('--output', default='batch36_2_audit.json')
    args = parser.parse_args(argv)
    baseline_path = Path(args.baseline)
    if not baseline_path.is_file():
        parser.error(f'36-1 기준 보고서가 없습니다: {baseline_path}')
    try:
        baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
        validate_baseline(baseline)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        parser.error(f'기준 보고서 검증 실패: {error}')

    permissive = run_audit(CASES, strict_runtime_validation=False)
    strict = run_audit(CASES, strict_runtime_validation=True)
    details = breakdown_action_results()
    result = compare_reports(baseline, permissive, strict, details)
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    old, new, safe = result['baseline_summary'], result['permissive_summary'], result['strict_summary']
    print('=== Batch36-2 이전/이후 자동 평가 ===')
    print('전체:', new['total_cases'], '/ 일반 변경:', new['changed_cases'],
          '/ 검증 변경:', new['changed_and_runtime_equivalent'])
    print('35-5 시점 기준:', old['changed_cases'], '변경 /',
          old['changed_and_runtime_equivalent'], '동등성 확인')
    print('strict 모드:', safe['changed_cases'], '변경 /',
          safe['changed_and_runtime_equivalent'], '동등성 확인 / 위반:',
          result['strict_unverified_change_violations'])
    print('strip 개선 4개:', [(x['id'], x['now_changed'], x['now_verified'])
                            for x in result['strip_cases']])
    print('검증 불가 3건 strict 롤백:',
          [(x['id'], x['strict_rollback_confirmed']) for x in result['async_cases']])
    print('no_safe_pattern 시도:', old['attempt_status_counts'].get('no_safe_pattern', 0),
          '→', new['attempt_status_counts'].get('no_safe_pattern', 0))
    print('보고서:', dest)
    failed = (new.get('failed_case_count', 0) or safe.get('failed_case_count', 0)
              or bool(result['strict_unverified_change_violations'])
              or bool(details['contract_violations'])
              or not all(x['now_changed'] and x['now_verified'] for x in result['strip_cases'])
              or not all(x['strict_rollback_confirmed'] for x in result['async_cases']))
    if failed:
        print('검증 문제 발생: 보고서의 failed_cases / strip_cases / async_cases 확인')
    return 2 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
