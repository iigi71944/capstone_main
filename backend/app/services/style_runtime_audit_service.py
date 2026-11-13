"""Offline, fixed-fixture differential checks for selected style transformers.

This intentionally checks a *finite collection of trusted built-in snippets*.
It does NOT execute user input, access the web, or certify arbitrary programs.

Run from backend/:
    python -m app.services.style_runtime_audit_service
    python -m app.services.style_runtime_audit_service --json
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
from dataclasses import dataclass
from typing import Callable

from app.services.improvement.safe_index_iteration_service import (
    transform_to_direct_iteration_style,
    transform_to_index_iteration_style,
)
from app.services.improvement.safe_list_comprehension_service import (
    transform_for_append_to_list_comprehension,
    transform_list_comprehension_to_for_append,
)
from app.services.improvement.safe_dict_comprehension_service import (
    transform_for_assignment_to_dict_comprehension,
    transform_dict_comprehension_to_for_assignment,
)

Transform = Callable[[str], str]

# The action names are the saved-style plan's internal action identifiers.
# The direct/index actions use their existing public identifiers.
_TRANSFORMS: dict[str, Transform] = {
    "create_direct_iteration": transform_to_direct_iteration_style,
    "create_index_iteration": transform_to_index_iteration_style,
    "create_safe_comprehension_collection": transform_for_append_to_list_comprehension,
    "create_safe_append_collection": transform_list_comprehension_to_for_append,
    "create_safe_dict_comprehension": transform_for_assignment_to_dict_comprehension,
    "create_safe_dict_loop": transform_dict_comprehension_to_for_assignment,
}


@dataclass(frozen=True)
class Probe:
    name: str
    action: str
    source: str
    must_change: bool


def _make_probes() -> tuple[Probe, ...]:
    probes: list[Probe] = []
    for idx, values in enumerate(([], [1], [1, 2, 2], [-3, 0, 5])):
        lit = repr(values)
        probes.extend((
            Probe(f"direct_{idx}", "create_direct_iteration",
                  f"values = {lit}\nfor i in range(len(values)):\n    print(i, values[i])\n__audit_result__ = len(values)\n", True),
            Probe(f"index_{idx}", "create_index_iteration",
                  f"values = {lit}\nfor item in values:\n    print(item)\n__audit_result__ = len(values)\n", True),
            Probe(f"list_collapse_{idx}", "create_safe_comprehension_collection",
                  f"values = {lit}\nresult = []\nfor x in values:\n    result.append(x * 2)\n__audit_result__ = result\n", True),
            Probe(f"list_expand_{idx}", "create_safe_append_collection",
                  f"values = {lit}\nresult = [x * 2 for x in values]\n__audit_result__ = result\n", True),
            Probe(f"dict_collapse_{idx}", "create_safe_dict_comprehension",
                  f"values = {lit}\nresult = {{}}\nfor x in values:\n    result[x] = x * x\n__audit_result__ = result\n", True),
            Probe(f"dict_expand_{idx}", "create_safe_dict_loop",
                  f"values = {lit}\nresult = {{x: x * x for x in values}}\n__audit_result__ = result\n", True),
        ))
    probes.extend((
        Probe("list_filter_collapse", "create_safe_comprehension_collection",
              "result = []\nfor x in [0, 1, 2, 3, 4]:\n    if x % 2 == 0:\n        result.append(x + 10)\n__audit_result__ = result\n", True),
        Probe("list_filter_expand", "create_safe_append_collection",
              "result = [x + 10 for x in [0, 1, 2, 3, 4] if x % 2 == 0]\n__audit_result__ = result\n", True),
        Probe("dict_filter_collapse", "create_safe_dict_comprehension",
              "result = {}\nfor x in [0, 1, 2, 3, 4]:\n    if x % 2 == 0:\n        result[x] = x + 10\n__audit_result__ = result\n", True),
        Probe("dict_filter_expand", "create_safe_dict_loop",
              "result = {x: x + 10 for x in [0, 1, 2, 3, 4] if x % 2 == 0}\n__audit_result__ = result\n", True),
        Probe("list_unpack_collapse", "create_safe_comprehension_collection",
              "result = []\nfor x, y in [(1, 5), (2, 6)]:\n    result.append(x + y)\n__audit_result__ = result\n", True),
        Probe("dict_unpack_expand", "create_safe_dict_loop",
              "result = {x: y + 1 for x, y in [(1, 3), (2, 4)]}\n__audit_result__ = result\n", True),
        Probe("list_unicode_collapse", "create_safe_comprehension_collection",
              "# 앞쪽\nresult = []\nfor 글자 in '가나':\n    result.append(글자 * 2)\n# 뒤쪽\n__audit_result__ = result\n", True),
        Probe("dict_unicode_expand", "create_safe_dict_loop",
              "# 시작\nresult = {글자: 글자 + '!' for 글자 in '가나'}\n# 끝\n__audit_result__ = result\n", True),
        Probe("index_for_else", "create_index_iteration",
              "values = [3, 8]\nfor item in values:\n    print(item)\nelse:\n    print('done')\n__audit_result__ = 1\n", True),
        Probe("direct_break_continue", "create_direct_iteration",
              "values = [1, 2, 3, 4]\nfor i in range(len(values)):\n    if values[i] == 2:\n        continue\n    if values[i] == 4:\n        break\n    print(values[i])\n__audit_result__ = 1\n", True),
        Probe("list_exception_expand", "create_safe_append_collection",
              "result = [10 // x for x in [5, 0, 1]]\n__audit_result__ = result\n", True),
        Probe("dict_exception_expand", "create_safe_dict_loop",
              "result = {x: 10 // x for x in [5, 0, 1]}\n__audit_result__ = result\n", True),
        # Negative checks ensure that unsafe constructions remain unchanged.
        Probe("index_skip_generator", "create_index_iteration",
              "values = (x for x in [1, 2])\nfor item in values:\n    print(item)\n__audit_result__ = 'done'\n", False),
        Probe("direct_skip_mutation", "create_direct_iteration",
              "values = [1, 2]\nfor i in range(len(values)):\n    values[i] += 1\n__audit_result__ = values\n", False),
        Probe("list_skip_result_dependency", "create_safe_comprehension_collection",
              "result = []\nfor x in [1, 2]:\n    result.append(result)\n__audit_result__ = len(result)\n", False),
        Probe("dict_skip_result_dependency", "create_safe_dict_comprehension",
              "result = {}\nfor x in [1, 2]:\n    result[x] = len(result)\n__audit_result__ = result\n", False),
        Probe("list_skip_nested_comprehension", "create_safe_append_collection",
              "result = [[y for y in [1, 2]] for x in [3, 4]]\n__audit_result__ = result\n", False),
        Probe("dict_skip_user_call", "create_safe_dict_loop",
              "def f(x):\n    return x * x\nresult = {x: f(x) for x in [1, 2]}\n__audit_result__ = result\n", False),
        Probe("list_skip_comment_in_loop", "create_safe_comprehension_collection",
              "result = []\nfor x in [1, 2]:\n    # keep me\n    result.append(x)\n__audit_result__ = result\n", False),
        Probe("dict_skip_comment_in_loop", "create_safe_dict_comprehension",
              "result = {}\nfor x in [1, 2]:\n    # keep me\n    result[x] = x\n__audit_result__ = result\n", False),
    ))
    return tuple(probes)


PROBES = _make_probes()


def _observe_fixture(source: str) -> dict:
    """Execute only the constant fixtures in PROBES; never arbitrary app input.

    Keep stdout, raised exception type/message, and the agreed observed value.
    Names generated by transforms are deliberately not part of this contract.
    """
    output = io.StringIO()
    namespace = {"__name__": "__capstone_audit__"}
    error: tuple[str, str] | None = None
    try:
        with contextlib.redirect_stdout(output):
            exec(compile(source, "<capstone-fixed-audit>", "exec"), namespace)
    except Exception as exc:
        error = (type(exc).__name__, str(exc))
    found = "__audit_result__" in namespace
    value = repr(namespace["__audit_result__"]) if found else None
    return {"stdout": output.getvalue(), "exception": error,
            "result_present": found, "result_repr": value}


def check_probe(probe: Probe) -> dict:
    """Run one trusted probe. Report failures without hiding transform errors."""
    if probe.action not in _TRANSFORMS:
        return {"name": probe.name, "action": probe.action, "ok": False,
                "error": "등록되지 않은 점검 액션"}
    try:
        ast.parse(probe.source)
        transformed = _TRANSFORMS[probe.action](probe.source)
        if not isinstance(transformed, str):
            raise TypeError("변환 결과가 문자열이 아닙니다.")
        ast.parse(transformed)
        observed_before = _observe_fixture(probe.source)
        observed_after = _observe_fixture(transformed)
        changed = transformed != probe.source
        conditions = {
            "changed_expected": changed == probe.must_change,
            "stdout_exception_result_equal": observed_before == observed_after,
        }
        return {"name": probe.name, "action": probe.action,
                "ok": all(conditions.values()), "changed": changed,
                "checks": conditions,
                "before": observed_before, "after": observed_after}
    except Exception as exc:
        return {"name": probe.name, "action": probe.action, "ok": False,
                "error": f"{type(exc).__name__}: {exc}"}


def run_runtime_audit() -> dict:
    results = [check_probe(probe) for probe in PROBES]
    failed = [result for result in results if not result["ok"]]
    return {
        "status": "ok" if not failed else "failed",
        "summary": {"total": len(results), "passed": len(results) - len(failed),
                    "failed": len(failed), "actions": len(_TRANSFORMS)},
        "failures": failed,
        "note": ("고정된 안전한 예제만 실행한 제한적 동등성 검사입니다. "
                 "임의의 사용자 코드 또는 전체 27개 액션의 의미 보존을 보증하지 않습니다."),
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="저장 스타일 변환 고정 예제 실행 동등성 점검")
    parser.add_argument("--json", action="store_true", help="전체 결과를 JSON으로 출력")
    args = parser.parse_args()
    report = run_runtime_audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        s = report["summary"]
        print("=== 저장 스타일 변환 실행 동등성 점검 ===")
        print(f"대상 액션 {s['actions']}종 | 고정 예제 {s['total']}개 | "
              f"통과 {s['passed']}개 | 실패 {s['failed']}개")
        print("상태:", "정상" if report["status"] == "ok" else "실패")
        for failure in report["failures"]:
            print(f"[실패] {failure['name']} / {failure['action']}: "
                  f"{failure.get('error', failure.get('checks'))}")
        print(report["note"])
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(_main())
