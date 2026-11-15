"""Batch 15 read-only regression audit; built-in cases only, no user code execution."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest

BACKEND = Path(__file__).resolve().parents[1]
for item in (BACKEND, BACKEND / 'tools', BACKEND / 'tests'):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import audit_transform_runtime_batch14 as previous

NEW_SUITES = (
    ('test_style_partial_conflict_batch15', 22),
    ('test_style_partial_conflict_integration_batch15', 7),
)


def audit() -> dict:
    report = previous.audit()
    summary = report['summary']
    issues = list(summary.get('audit_issues', []))
    total = passed = 0
    for module, expected in NEW_SUITES:
        suite = unittest.defaultTestLoader.loadTestsFromName(module)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            result = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)
        ok = result.wasSuccessful() and result.testsRun == expected and not result.skipped
        total += result.testsRun
        passed += (result.testsRun if ok else
                   result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped))
        if not ok:
            issues.append(f'{module}: expected {expected} passing cases: ' + stream.getvalue()[-2500:])
    summary['batch15_partial_conflict_tests'] = total
    summary['batch15_partial_conflict_tests_passed'] = passed
    summary['audit_issues'] = issues
    report['extension_note'] = (
        'Batch 15 extends Batch 14 to conservative per-top-level-scope AST reversion '
        'reporting. It never establishes general semantic equivalence, changes '
        'no saved style schema, and creates no new tag links.'
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    report = audit()
    summary = report['summary']
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print('=== 15차 자동 변환 부분 충돌 검사 ===')
        print(f"전체 태그 {summary['tags']} / 연결 {summary['linked']} / 비교 전용 {summary['compare_only']}")
        print(f"13차 대표 검사 {summary['representative_tests_passed']}/{summary['representative_tests']}")
        print(f"14차 충돌·검증 검사 {summary['batch14_conflict_tests_passed']}/{summary['batch14_conflict_tests']}")
        print(f"15차 부분 충돌 검사 {summary['batch15_partial_conflict_tests_passed']}/{summary['batch15_partial_conflict_tests']}")
        for issue in summary['audit_issues']:
            print('검증 문제:', issue)
    return 0 if (
        summary['registry_status'] == 'ok'
        and not summary['registry_issues']
        and not summary['audit_issues']
        and summary['tags'] == 102
        and summary['linked'] == 78
        and summary['compare_only'] == 24
        and summary['by_status']['three_patterns_verified'] == 78
        and summary['representative_tests'] == 234
        and summary['representative_tests_passed'] == 234
        and summary['batch14_conflict_tests'] == 16
        and summary['batch14_conflict_tests_passed'] == 16
        and summary['batch15_partial_conflict_tests'] == 29
        and summary['batch15_partial_conflict_tests_passed'] == 29
    ) else 1


if __name__ == '__main__':
    raise SystemExit(main())
