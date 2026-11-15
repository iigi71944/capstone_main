"""Batch 14 runtime-action conflict audit, with Batch 13 tag baseline retained.

Runs only fixed unittest fixtures; never executes arbitrary user input.
The 234 representative cases are inherited from the Batch 13 evidence audit.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest

BACKEND = Path(__file__).resolve().parents[1]
for folder in (BACKEND, BACKEND / 'tools', BACKEND / 'tests'):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import audit_transform_three_patterns_batch13 as previous


def audit() -> dict:
    previous_report = previous.audit()
    s = previous_report['summary']
    failures = list(s.get('audit_issues', []))

    suite = unittest.defaultTestLoader.loadTestsFromName(
        'test_style_action_conflict_batch14')
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        result = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)
    passed = result.wasSuccessful() and result.testsRun == 16 and not result.skipped
    if not passed:
        failures.append('14차 변환 충돌 테스트 실패: ' + stream.getvalue()[-2500:])
    s['batch14_conflict_tests'] = result.testsRun
    s['batch14_conflict_tests_passed'] = result.testsRun if passed else (
        result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped))
    s['batch14_previous_linked'] = s['linked']
    s['audit_issues'] = failures
    previous_report['extension_note'] = (
        'Batch 14 adds action-checkpoint conflict accounting and rejects a '
        'contradictory different/True verifier. No tag is newly linked; '
        'the 234 Batch 13 per-tag cases and 16 fixed Batch 14 conflict '
        'tests are representative regression evidence, not proof of '
        'semantic equivalence for arbitrary user code.'
    )
    return previous_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--json', action='store_true')
    options = parser.parse_args()
    report = audit()
    s = report['summary']
    if options.output:
        options.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if options.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print('=== 14차 자동 변환 충돌·검증 결과 감사 ===')
        print(f"전체 태그 {s['tags']} / 연결 {s['linked']} / 비교 전용 {s['compare_only']}")
        print(f"기존 대표 검사 {s['representative_tests_passed']}/{s['representative_tests']}")
        print(f"14차 충돌·검증 회귀 검사 {s['batch14_conflict_tests_passed']}/{s['batch14_conflict_tests']}")
        for issue in s['audit_issues']:
            print('검증 문제:', issue)
    return 0 if (
        s['registry_status'] == 'ok'
        and not s['registry_issues']
        and not s['audit_issues']
        and s['tags'] == 102
        and s['linked'] == 78
        and s['compare_only'] == 24
        and s['by_status']['three_patterns_verified'] == 78
        and s['representative_tests'] == 234
        and s['representative_tests_passed'] == 234
        and s['batch14_conflict_tests'] == 16
        and s['batch14_conflict_tests_passed'] == 16
    ) else 1


if __name__ == '__main__':
    raise SystemExit(main())
