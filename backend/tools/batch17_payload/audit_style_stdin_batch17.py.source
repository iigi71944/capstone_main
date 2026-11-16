"""Audit Batch 17 stdin-aware runtime / function verification using fixed fixtures."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import unittest

BACKEND=Path(__file__).resolve().parents[1]
for p in (BACKEND,BACKEND/'tests'):
    if str(p) not in sys.path: sys.path.insert(0,str(p))
from app.services.style_tag_transform_map_service import CREATE_ACTION_BY_TAG
from app.schemas.style_apply import StyleApplyRequest, FunctionTestCase

def audit()->dict:
    suite=unittest.defaultTestLoader.loadTestsFromName('test_style_stdin_batch17')
    runner=unittest.TextTestRunner(stream=sys.stderr,verbosity=0)
    result=runner.run(suite)
    fail=len(result.failures)+len(result.errors)
    return {'revision':'batch17','tested':result.testsRun,'passed':result.testsRun-fail,
            'failed':fail,'linked_tags':len(CREATE_ACTION_BY_TAG),
            'request_stdin':'stdin' in StyleApplyRequest.model_fields,
            'function_stdin':'stdin' in FunctionTestCase.model_fields,
            'errors':[str(case) for case,_ in result.failures+result.errors]}

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path);args=p.parse_args()
    r=audit()
    if args.output:args.output.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print('=== 17차 표준 입력(stdin) 실행 검증 감사 ===')
    print(f"신규 검사 {r['passed']}/{r['tested']} 통과 / 기존 연결 태그 {r['linked_tags']}개")
    for issue in r['errors']:print('오류:',issue)
    return 0 if not r['failed'] and r['tested']>=28 and r['linked_tags']==78 and r['request_stdin'] and r['function_stdin'] else 1
if __name__=='__main__':raise SystemExit(main())
