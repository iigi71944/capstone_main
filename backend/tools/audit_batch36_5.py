"""Batch36-5 final safety/style benchmark and Word-ready verified example export.

Use the same 50 authored fixtures, not external code. Only changes actually
observed equivalent by the existing strict runtime verifier qualify as examples.
Generated examples include the exact saved-style source, target source, and
transformed source; no theoretical after-code is substituted.

From backend working directory:
    python -m tools.audit_batch36_5 --baseline batch36_4_audit.json \\
        --output batch36_5_audit.json --examples batch36_5_verified_examples.json
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from tools.audit_batch36_1 import run_audit
from tools.batch36_1_cases import CASES

VERSION = 1
MIN_EXAMPLES = 30


def validate_baseline(report: dict) -> dict:
    if not isinstance(report, dict) or report.get('report_version') != 1:
        raise ValueError('36-4 보고서 버전이 유효하지 않습니다.')
    current = report.get('current')
    strict = report.get('strict')
    contract = report.get('contract')
    if not isinstance(current, dict) or not isinstance(strict, dict) or not isinstance(contract, dict):
        raise ValueError('36-4 보고서 집계가 누락되었습니다.')
    if (contract.get('same_50_ids') is not True
            or contract.get('strict_unverified_changed_cases') != []
            or strict.get('unverified_changed_cases') != []):
        raise ValueError('36-4 엄격 검증 또는 동일 사례 조건을 확인하지 못했습니다.')
    for key in ('changed', 'verified_changes', 'no_safe_pattern', 'preflight_skipped'):
        if type(current.get(key)) is not int or current[key] < 0:
            raise ValueError('36-4 집계 값 오류: ' + key)
    if (current['changed'] > len(CASES)
            or current['verified_changes'] > current['changed']
            or current.get('failed_cases') != []
            or strict.get('failed_cases') != []):
        raise ValueError('36-4 실패 사례 또는 일치하지 않는 집계')
    composite = report.get('composite_R45')
    if (not isinstance(composite, dict) or composite.get('changed') is not True
            or composite.get('verification_status') != 'equivalent'):
        raise ValueError('36-4 R45 복합 변환 검증이 누락되었습니다.')
    return current


def collect_verified_examples(strict_audit: dict, *, analyze=None, apply=None) -> list[dict]:
    """Reapply strict case and compare with the independent case-audit hash.

    The double execution is deliberate: Word export must reflect real code,
    not merely a diff excerpt (which might be truncated) or an assumption.
    """
    if analyze is None:
        from app.services.style_diff_service import analyze_code_style
        analyze = analyze_code_style
    if apply is None:
        from app.services.style_apply_service import apply_coding_style
        apply = apply_coding_style
    rows = strict_audit.get('cases', [])
    if len(rows) != len(CASES) or [r.get('id') for r in rows] != [c.case_id for c in CASES]:
        raise ValueError('50개 사례 ID가 일치하지 않습니다.')
    examples = []
    for case, row in zip(CASES, rows):
        if not (row.get('changed') is True
                and row.get('verification_status') == 'equivalent'
                and row.get('verification_equivalent') is True
                and not row.get('errors') and case.purpose != 'negative_shape'):
            continue
        saved = analyze(case.style_code)
        style = {
            'id': case.case_id, 'name': case.name,
            'description': '36-5 verified authored fixture',
            'syntax_tags': saved['syntax_tags'],
            'concept_tags': saved['concept_tags'],
            'metrics': dict(saved['metrics']),
            'created_at': '2026-11-18T00:00:00Z',
        }
        if case.version == 'v1':
            style['metrics_version'] = 1
        kwargs = {'code': case.target_code, 'style': style,
                  'strict_runtime_validation': True}
        if case.stdin is not None:
            kwargs['stdin'] = case.stdin
        after, _, applied_rules, warnings, final_diff, verification = apply(**kwargs)
        if not (isinstance(after, str) and after != case.target_code
                and isinstance(verification, dict)
                and verification.get('status') == 'equivalent'
                and verification.get('equivalent') is True
                and sha256(after.encode('utf-8')).hexdigest() == row.get('transformed_sha256')):
            raise ValueError(f'{case.case_id}: export differs from strict audited execution')
        quality = final_diff.get('style_alignment_quality')
        if not isinstance(quality, dict) or quality.get('version') != 1:
            raise ValueError(f'{case.case_id}: missing final style quality evidence')
        examples.append({
            'id': case.case_id, 'group': case.group, 'title': case.name,
            'style_source_code': case.style_code,
            'target_source_code': case.target_code,
            'actual_transformed_code': after,
            'saved_syntax_tags': sorted(x['tag'] for x in saved['syntax_tags']),
            'saved_concept_tags': sorted(x['tag'] for x in saved['concept_tags']),
            'resolved_tags': row.get('resolved_tags', []),
            'introduced_missing_tags': row.get('introduced_missing_tags', []),
            'final_missing_tags': row.get('final_missing_tags', []),
            'quality_evidence': quality,
            'execution_verification_status': 'equivalent',
            'runtime_scope': 'observed sample-input execution only; no universal equivalence guarantee',
            'applied_rule_count': len(applied_rules),
            'stdin_example': case.stdin,
            'reference_origin': 'Batch36-1 authored deterministic fixture',
        })
    return examples


def make_report(base: dict, normal: dict, strict: dict, examples: list[dict]) -> dict:
    prev = validate_baseline(base)
    if (normal.get('case_count') != len(CASES)
            or strict.get('case_count') != len(CASES)):
        raise ValueError('The full 50-case comparison is required')
    expected_ids = [case.case_id for case in CASES]
    if ([r.get('id') for r in normal.get('cases', [])] != expected_ids
            or [r.get('id') for r in strict.get('cases', [])] != expected_ids):
        raise ValueError('Audited case IDs differ from baseline fixture IDs')
    ns, ss = normal['summary'], strict['summary']
    strict_unverified = [r['id'] for r in strict['cases'] if r.get('changed') and
                         not (r.get('verification_status') == 'equivalent'
                              and r.get('verification_equivalent') is True)]
    if len({item['id'] for item in examples}) != len(examples):
        raise ValueError('Duplicate verified export IDs')
    gaps = Counter()
    # Quality indicators below describe only the exported strictly verified
    # transformations; don't silently extrapolate them to all 50 cases.
    tag_gaps = [ex['quality_evidence']['tag_gap'] for ex in examples]
    preferences = [ex['quality_evidence']['default_form_preferences'] for ex in examples]
    verified_quality = {
        'denominator': len(examples),
        'scope': 'strictly verified changed examples only',
        'cases_with_observed_style_progress': sum(
            ex['quality_evidence']['conclusion'] == 'verified_observed_progress'
            for ex in examples),
        'cases_without_measured_style_progress': sum(
            ex['quality_evidence']['conclusion'] == 'verified_change_without_measured_progress'
            for ex in examples),
        'resolved_tag_occurrences': sum(g['resolved_count'] for g in tag_gaps),
        'introduced_missing_tag_occurrences': sum(g['introduced_count'] for g in tag_gaps),
        'default_preference_opportunities': sum(p['evaluated'] for p in preferences),
        'default_preference_improved': sum(p['improved'] for p in preferences),
        'default_preference_regressed': sum(p['regressed'] for p in preferences),
    }
    for r in normal['cases']:
        for name in r.get('final_missing_tags', []):
            gaps[name] += 1
    return {
        'report_version': VERSION,
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': '50 authored deterministic Python fixtures, backend only',
        'baseline_commit': 'b258464',
        'baseline': {key: prev[key] for key in ('changed', 'verified_changes', 'no_safe_pattern', 'preflight_skipped')},
        'current': {
            'changed': ns['changed_cases'],
            'verified_changes': ns['changed_and_runtime_equivalent'],
            'not_verified_changes': ns['changed_but_runtime_not_verified'],
            'no_safe_pattern': ns['attempt_status_counts'].get('no_safe_pattern', 0),
            'preflight_skipped': ns['attempt_status_counts'].get('skipped_shape_preflight', 0),
            'resolved_tags': ns['resolved_missing_tag_instances'],
            'introduced_tags': ns['newly_missing_tag_instances'],
            'failed_case_ids': ns['failed_case_ids'],
            'most_frequent_final_missing_tags': [
                {'tag': tag, 'cases': count} for tag, count in gaps.most_common(15)],
        },
        'strict': {
            'changed': ss['changed_cases'],
            'verified_changes': ss['changed_and_runtime_equivalent'],
            'unverified_changed_case_ids': strict_unverified,
            'failed_case_ids': ss['failed_case_ids'],
            'async_rollback_ids': [
                row['id'] for row in strict['cases'] if row['id'] in {'R04', 'R05', 'R06'}
                and row.get('verification_status') == 'not_verified'
                and row.get('changed') is False],
        },
        'deltas': {
            'changed': ns['changed_cases'] - prev['changed'],
            'verified_changes': ns['changed_and_runtime_equivalent'] - prev['verified_changes'],
            'no_safe_pattern': ns['attempt_status_counts'].get('no_safe_pattern', 0) - prev['no_safe_pattern'],
        },
        'verified_quality_evidence': verified_quality,
        'verified_word_examples': {
            'count': len(examples), 'minimum_required': MIN_EXAMPLES,
            'complete': len(examples) >= MIN_EXAMPLES,
            'ids': [e['id'] for e in examples],
            'groups': dict(Counter(e['group'] for e in examples)),
            'criteria': 'actual strict-mode change + observed runtime equivalence + exact output hash match',
        },
        'contract': {
            'same_50_ids': True,
            'no_strict_unverified_changes': not strict_unverified,
            'no_case_errors': not ns['failed_case_ids'] and not ss['failed_case_ids'],
            'minimum_examples_met': len(examples) >= MIN_EXAMPLES,
            'R08_no_op': next(r for r in normal['cases'] if r['id'] == 'R08')['changed'] is False,
            'R43_verified': next(r for r in strict['cases'] if r['id'] == 'R43')['verification_status'] == 'equivalent',
            'R45_verified': next(r for r in strict['cases'] if r['id'] == 'R45')['verification_status'] == 'equivalent',
        },
        'limitations': [
            'This benchmark was authored for the project; it is not a real-world corpus.',
            'Execution equivalence describes observed test inputs only.',
            'The code examples do not cover UI formatting, file I/O, or arbitrary Python programs.',
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='36-5 final evidence and verified Word-code preparation')
    parser.add_argument('--baseline', default='batch36_4_audit.json')
    parser.add_argument('--output', default='batch36_5_audit.json')
    parser.add_argument('--examples', default='batch36_5_verified_examples.json')
    args = parser.parse_args(argv)
    try:
        baseline = json.loads(Path(args.baseline).read_text(encoding='utf-8'))
        validate_baseline(baseline)
        normal = run_audit(CASES, strict_runtime_validation=False)
        strict = run_audit(CASES, strict_runtime_validation=True)
        examples = collect_verified_examples(strict)
        report = make_report(baseline, normal, strict, examples)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        parser.error(f'36-5 평가 실패: {exc}')
    # Validate before saving either artifact; do not publish a misleading set.
    if not all(report['contract'].values()):
        parser.error('36-5 안전성/예제 수량 계약 불일치: ' + repr(report['contract']))
    for filename, payload in (
        (args.output, report),
        (args.examples, {
            'version': VERSION,
            'benchmark_origin': 'authored deterministic fixtures; not a real-world corpus',
            'verification_scope': 'strict-mode observed runtime equivalence',
            'count': len(examples), 'examples': examples,
        }),
    ):
        out = Path(filename)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('=== Batch36-5 최종 품질/예제 검증 ===')
    print('코드 변경:', report['baseline']['changed'], '→', report['current']['changed'])
    print('실행 동등성 확인:', report['baseline']['verified_changes'], '→', report['current']['verified_changes'])
    print('no_safe_pattern:', report['baseline']['no_safe_pattern'], '→', report['current']['no_safe_pattern'])
    print('엄격 검증 미확인 변경:', report['strict']['unverified_changed_case_ids'])
    print('Word 예제용 실제 검증 세트:', report['verified_word_examples']['count'])
    print('평가 보고서:', args.output)
    print('예제 원본:', args.examples)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
