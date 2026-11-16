"""Read-only Batch 16 strict verification audit (test fixtures only)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import unittest

BACKEND = Path(__file__).resolve().parents[1]
for location in (BACKEND, BACKEND / 'tests'):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from app.schemas.style_apply import StyleApplyRequest
from app.services.style_apply_service import apply_coding_style
from app.services.style_tag_transform_map_service import CREATE_ACTION_BY_TAG


def audit() -> dict:
    suite = unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromName('test_style_strict_validation_batch16'))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromName('test_style_strict_installer_batch16'))
    runner = unittest.TextTestRunner(stream=sys.stderr, verbosity=0)
    result = runner.run(suite)
    tested = result.testsRun
    fail = len(result.failures) + len(result.errors)
    return {'revision':'batch16', 'tests':tested, 'passed':tested-fail,
            'failed':fail, 'registry_linked':len(CREATE_ACTION_BY_TAG),
            'request_has_strict_option': 'strict_runtime_validation' in StyleApplyRequest.model_fields,
            'service_accepts_strict_option': 'strict_runtime_validation' in apply_coding_style.__code__.co_varnames,
            'issues':[str(case) for case, _ in result.failures+result.errors]}


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--output', type=Path)
    args=p.parse_args()
    report=audit()
    if args.output:
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2), encoding='utf-8')
    print('=== 16차 엄격 실행 검증 통합 감사 ===')
    print(f"검증 {report['passed']}/{report['tests']} 통과, 기존 연결 태그 {report['registry_linked']}개")
    for issue in report['issues']:
        print('오류:',issue)
    return 0 if (report['failed']==0 and report['tests']>=27
            and report['registry_linked']==78 and report['request_has_strict_option']
            and report['service_accepts_strict_option']) else 1


if __name__=='__main__':
    raise SystemExit(main())
