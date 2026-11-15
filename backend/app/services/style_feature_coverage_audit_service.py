"""Read-only, *curated-fixture only* coverage audit for the 18 formerly planned tags.

From the project backend directory:
    python -m app.services.style_feature_coverage_audit_service
    python -m app.services.style_feature_coverage_audit_service --json

No user-supplied Python code is accepted by this module. The 18 examples are
fixed source strings reviewed with this repository. The module does not mutate
project files, save styles, or import user-provided scripts. It is NOT a
security sandbox and cannot prove arbitrary-program semantic equivalence.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
from dataclasses import dataclass
import io
import json
from typing import Any

from app.services.style_tag_transform_map_service import get_create_action_for_tag
from app.services.style_transform_plan_service import build_transform_plan
from app.services.style_apply_service import _get_transform_function
from app.services.tag_rule_service import SYNTAX_TAG_RULES, CONCEPT_TAG_RULES


@dataclass(frozen=True)
class FixedExample:
    tag: str
    action: str
    code: str
    marker: str


# Exactly 18 tag entries from auto-transform batches 1-4.
# These are built-in, static fixtures, not arbitrary submitted Python code.
_EXAMPLES: tuple[FixedExample, ...] = (
    FixedExample('세트 컴프리헨션', 'create_safe_set_comprehension',
        'result=set()\nfor x in [1,2,3]:\n    result.add(x*x)\n', 'result = {'),
    FixedExample('lambda식', 'create_safe_lambda_expression',
        'def f(x):\n    return x*x\nresult=f(3)\n', 'lambda x:'),
    FixedExample('타입 힌트 사용', 'create_safe_local_annotation',
        'def f():\n    x=10\n    return x\nresult=f()\n', 'x: int = 10'),
    FixedExample('타입 명시 코드 구조', 'create_safe_local_annotation',
        'def f():\n    x="hi"\n    return x\nresult=f()\n', 'x: str ='),
    FixedExample('패턴 매칭', 'create_safe_pattern_matching',
        'v=2\nif v==1:\n    result="a"\nelif v==2:\n    result="b"\nelse:\n    result="c"\n', 'match v:'),
    FixedExample('패턴 매칭 구조', 'create_safe_pattern_matching',
        'v=1\nif v==1:\n    result=10\nelif v==2:\n    result=20\nelse:\n    result=0\n', 'match v:'),
    FixedExample('예외 처리', 'create_safe_explicit_exception',
        'import contextlib\nwith contextlib.suppress(ValueError):\n    print(1)\nresult=5\n', 'except ValueError:'),
    FixedExample('예외 처리 포함 구조', 'create_safe_explicit_exception',
        'import contextlib\nwith contextlib.suppress(TypeError):\n    print(2)\nresult=7\n', 'except TypeError:'),
    FixedExample('함수 매개변수 활용 구조', 'create_safe_keyword_call',
        'def add(a,b):\n    return a+b\nresult=add(2,3)\n', 'add(a=2, b=3)'),
    FixedExample('객체 접근 중심 구조', 'create_safe_direct_attribute',
        'class Item:\n    def __init__(self):\n        self.color="red"\nobj=Item()\nresult=getattr(obj,"color")\n', 'obj.color'),
    FixedExample('데코레이터 사용', 'create_safe_method_decorator',
        'class A:\n    def f(x):\n        return x+1\n    f=staticmethod(f)\nresult=A.f(2)\n', '@staticmethod'),
    FixedExample('방어적 프로그래밍 구조', 'create_safe_next_guard',
        'it=iter([])\nresult=next(it,"done")\n', 'except StopIteration:'),
    FixedExample('함수 호출 중심 구조', 'create_safe_operator_call',
        'import operator\na=2\nb=3\nresult=a+b\n', 'operator.add(a, b)'),
    FixedExample('함수 정의', 'create_safe_lambda_function',
        'f=lambda x:x*x\nresult=f(3)\n', 'def f('),
    FixedExample('단일 책임 함수 구조', 'create_safe_validation_helper',
        'def f(x):\n    if x < 0:\n        raise ValueError("negative")\n    return x*2\nresult=f(3)\n', 'def __capstone_validate_x'),
    FixedExample('모듈 의존 구조', 'create_safe_math_module_import',
        'def f(x):\n    from math import sqrt\n    return sqrt(x)\nresult=f(9)\n', 'import math'),
    FixedExample('클래스 정의', 'create_safe_explicit_class',
        'Box=type("Box",(),{"side":2})\nresult=Box.side\n', 'class Box:'),
    FixedExample('클래스 중심 코드 구조', 'create_safe_class_methods',
        'def add(x):\n    return x+1\nTool=type("Tool",(),{"add":staticmethod(add)})\nresult=Tool.add(3)\n', 'class Tool:'),
)


@dataclass(frozen=True)
class SkipExample:
    action: str
    code: str
    description: str


_SKIP_EXAMPLES: tuple[SkipExample, ...] = (
    SkipExample('create_safe_set_comprehension',
        'set=lambda: []\nresult=set()\nfor x in [1,2]:\n    result.add(x)\n', 'set 재정의'),
    SkipExample('create_safe_lambda_expression',
        '@wrapper\ndef f(x):\n    return x\n', '데코레이터를 가진 함수'),
    SkipExample('create_safe_pattern_matching',
        'v=True\nif v==True:\n    result=1\nelse:\n    result=2\n', '불리언 비교'),
    SkipExample('create_safe_explicit_exception',
        'import contextlib as ctx\nwith ctx.suppress(ValueError):\n    print(1)\n', '별칭 사용'),
    SkipExample('create_safe_keyword_call',
        'def f(a,b=2):\n    return a+b\nresult=f(1,3)\n', '기본 매개변수'),
    SkipExample('create_safe_direct_attribute',
        'class C: pass\nobj=C()\nresult=getattr(obj,"missing",None)\n', 'getattr 기본값'),
    SkipExample('create_safe_method_decorator',
        'def f(x):\n    return x\nf=staticmethod(f)\n', '클래스 밖 데코레이터'),
    SkipExample('create_safe_next_guard',
        'it=iter([])\nresult=next(it)\n', '기본값 없는 next'),
    SkipExample('create_safe_operator_call',
        'a=2\nb=3\nresult=a+b\n', 'operator 미import'),
    SkipExample('create_safe_local_annotation',
        'x=10\n', '전역 변수 주석'),
    SkipExample('create_safe_validation_helper',
        'def f(x):\n    """doc"""\n    if x<0:\n        raise ValueError("negative")\n    return x*2\n', 'docstring 있는 함수'),
    SkipExample('create_safe_math_module_import',
        'def f(x):\n    from math import sqrt as s\n    return s(x)\n', 'math 별칭 import'),
    SkipExample('create_safe_explicit_class',
        'Box=type("Box",(object,),{"side":2})\n', '상속 클래스'),
    SkipExample('create_safe_class_methods',
        'Tool=type("Tool",(),{"add":staticmethod(add)})\n', '미정의 메서드'),
)


def _plan_for_single_tag(tag: str) -> dict[str, Any]:
    if tag in SYNTAX_TAG_RULES:
        syntax, concept = [{'tag': tag}], []
    elif tag in CONCEPT_TAG_RULES:
        syntax, concept = [], [{'tag': tag}]
    else:
        raise KeyError(f'등록되지 않은 태그: {tag}')
    return build_transform_plan({
        'missing_syntax_tags': syntax,
        'missing_concept_tags': concept,
        'style_syntax_names': set(),
        'style_concept_names': set(),
        'target_syntax_names': set(),
        'target_concept_names': set(),
        'style_metrics': {},
        'target_analysis': {'metrics': {}},
    })


def _observe_fixed_code(code: str) -> tuple[Any, ...]:
    """Execute only compile-time embedded, short, controlled audit examples.

    The fixture sources use only literals, math/operator/contextlib and local
    definitions. Do not expose this function as a user-code evaluator.
    """
    out = io.StringIO()
    values: dict[str, Any] = {}
    with contextlib.redirect_stdout(out):
        try:
            exec(compile(code, '<trusted-audit-fixture>', 'exec'), values)
            error = None
        except Exception as exc:  # comparison includes error shape
            error = (type(exc).__name__, str(exc))
    value = values.get('result', None)
    return (out.getvalue(), error, type(value).__name__, repr(value))


def audit_full_feature_coverage() -> dict[str, Any]:
    """Check action registry, plan dispatch, actual rewrite, fixed-fixture output.

    Returns structured data so the CLI and tests can report exact failures.
    No existing project file or saved style is modified.
    """
    rows = []
    skips = []
    for case in _EXAMPLES:
        reasons: list[str] = []
        mapping = get_create_action_for_tag(case.tag)
        if mapping != case.action:
            reasons.append(f'액션 매핑 불일치: {mapping!r} (예상 {case.action!r})')
        try:
            plan = _plan_for_single_tag(case.tag)
            actions = [item.get('action') for item in plan.get('actions', [])]
            if case.action not in actions:
                reasons.append(f'변환 계획에서 액션 미선택: {actions!r}')
        except (TypeError, ValueError, KeyError) as exc:
            reasons.append(f'변환 계획 구성 오류: {type(exc).__name__}: {exc}')
            actions = []
        func = _get_transform_function(case.action)
        changed = False
        same_output: bool | None = None
        if not callable(func):
            reasons.append('변환 실행 함수 연결 누락')
        else:
            try:
                output = func(case.code)
                if not isinstance(output, str):
                    reasons.append('변환 결과가 문자열이 아님')
                else:
                    ast.parse(output)
                    changed = ast.dump(ast.parse(case.code)) != ast.dump(ast.parse(output))
                    if not changed:
                        reasons.append('고정 예제에서 실제 코드 변경이 발생하지 않음')
                    if case.marker not in output:
                        reasons.append(f'예상 변환 표현 누락: {case.marker!r}')
                    if changed:
                        same_output = _observe_fixed_code(case.code) == _observe_fixed_code(output)
                        if not same_output:
                            reasons.append('고정 예제 실행 결과가 다름')
            except (Exception, KeyboardInterrupt) as exc:
                reasons.append(f'변환/비교 실행 오류: {type(exc).__name__}: {exc}')
        rows.append({
            'tag': case.tag,
            'action': case.action,
            'selected_action': case.action in actions,
            'changed': changed,
            'equivalent': same_output,
            'status': 'passed' if not reasons else 'failed',
            'reasons': reasons,
        })

    for case in _SKIP_EXAMPLES:
        reasons = []
        func = _get_transform_function(case.action)
        if not callable(func):
            reasons.append('변환 실행 함수 연결 누락')
        else:
            try:
                result = func(case.code)
                if result != case.code:
                    reasons.append('위험 패턴을 변경함 (원본 유지 필요)')
            except Exception as exc:
                reasons.append(f'변환기 예외: {type(exc).__name__}: {exc}')
        skips.append({
            'action': case.action,
            'case': case.description,
            'status': 'passed' if not reasons else 'failed',
            'reasons': reasons,
        })

    failed = sum(x['status'] == 'failed' for x in (*rows, *skips))
    return {
        'status': 'ok' if failed == 0 else 'issues_found',
        'summary': {
            'positive_cases': len(rows),
            'negative_cases': len(skips),
            'passed': len(rows) + len(skips) - failed,
            'failed': failed,
        },
        'positive': rows,
        'negative': skips,
        'note': (
            '사전에 내장된 제한된 예제만 검사합니다. 실제 프로젝트의 전체 변환기, '
            '임의의 사용자 코드, 외부 부작용의 의미 보존을 보증하지 않습니다.'
        ),
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description='캡스톤 신규 18개 태그 실행 연계 점검')
    parser.add_argument('--json', action='store_true', help='JSON 상세 출력')
    args = parser.parse_args()
    report = audit_full_feature_coverage()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        summary = report['summary']
        print('=== 자동 변환 18개 태그 통합 점검 ===')
        print(f"태그별 성공 예제 {summary['positive_cases']}개 | "
              f"위험 패턴 제외 {summary['negative_cases']}개 | "
              f"통과 {summary['passed']}개 | 실패 {summary['failed']}개")
        print('상태:', '정상' if report['status'] == 'ok' else '점검 필요')
        for part in ('positive', 'negative'):
            for row in report[part]:
                if row['status'] != 'passed':
                    name = row.get('tag', row.get('case', ''))
                    print(f"[FAIL] {name}: {'; '.join(row['reasons'])}")
        print(report['note'])
    return 0 if report['status'] == 'ok' else 1


if __name__ == '__main__':
    raise SystemExit(_main())
