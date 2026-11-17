"""32차: 102개 태그의 *관측된* 실제 코드 변경과 안전성 감사.

31차의 306개 대표 테스트는 테스트 성공 여부만 나타냅니다. 이 감사는
각 대표 테스트를 별도로 재실행하면서 해당 태그의 실제 dispatcher
변환기 호출/반환값을 관측하여 편집률과 적용 서비스 상태를 구분합니다.

Only trusted, repository-bundled unittest fixtures are used. This is not a
representative sampling of arbitrary user programs or a proof of semantic
correctness. No user-entered source is run. Optional runtime checks use the
existing restricted verifier and must be explicitly requested.
"""
from __future__ import annotations

import argparse
import ast
import inspect
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
for path in (BACKEND, BACKEND / "tests", BACKEND / "tools"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import audit_transform_batch31 as previous
import audit_transform_three_patterns as representative
from app.services.style_apply_service import _apply_style_action, _get_transform_function
from app.services.style_tag_transform_map_service import CREATE_ACTION_BY_TAG

CASE_LEVELS = ("basic", "additional", "complex")
MAX_PROBE_SOURCE_CHARS = 40_000


class TransformerTrace:
    """Observe one concrete Python function without patching its behavior.

    sys.setprofile records only the function's exact code object; helpers,
    other actions and subprocesses do not count as evidence for this tag.
    """

    def __init__(self, transformer):
        code_obj = getattr(transformer, "__code__", None)
        self.code_obj = code_obj
        try:
            self.parameter_names = tuple(inspect.signature(transformer).parameters)
        except (ValueError, TypeError):
            self.parameter_names = ("code",)
        self.pending: dict[int, str | None] = {}
        self.calls = 0
        self.changed = 0
        self.unchanged = 0
        self.invalid = 0
        self.non_string = 0
        self.sample: tuple[str, str] | None = None

    def __call__(self, frame, event, arg):
        if frame.f_code is not self.code_obj:
            return
        if event == "call":
            source = next((frame.f_locals[name] for name in self.parameter_names
                           if type(frame.f_locals.get(name)) is str), None)
            self.pending[id(frame)] = source
            return
        if event != "return":
            return
        source = self.pending.pop(id(frame), None)
        if source is None:
            return
        self.calls += 1
        if type(arg) is not str:
            self.non_string += 1
        elif source == arg:
            self.unchanged += 1
        else:
            self.changed += 1
            try:
                ast.parse(arg)
            except (SyntaxError, ValueError, TypeError):
                self.invalid += 1
            else:
                if (self.sample is None and len(source) <= MAX_PROBE_SOURCE_CHARS
                        and len(arg) <= MAX_PROBE_SOURCE_CHARS):
                    self.sample = (source, arg)


def trace_representative_case(test_id: str, transformer) -> tuple[bool, str, TransformerTrace]:
    """Run a known unittest ID with a temporary read-only profiler."""
    trace = TransformerTrace(transformer)
    old_profile = sys.getprofile()
    if trace.code_obj is None:
        ok, detail = representative._run_case(test_id)
        return ok, detail, trace
    try:
        sys.setprofile(trace)
        ok, detail = representative._run_case(test_id)
    finally:
        sys.setprofile(old_profile)
    return ok, detail, trace


def check_apply_action(tag: str, action: str, original: str) -> str:
    """Use the REAL production action applicator, without executing code."""
    try:
        changed, ledger = _apply_style_action(
            code=original,
            action_item={"tag": tag, "action": action, "reason": "32차 대표 패턴 검사"},
            applied_rules=[], warnings=[],
        )
    except Exception as exc:
        return "applicator_exception:" + type(exc).__name__
    status = ledger.get("status", "unknown")
    return "applied" if status == "applied" and changed != original else str(status)


def _runtime_classify(original: str, edited: str) -> str:
    """Opt-in only; never bypass the existing runtime restriction."""
    from app.services.execution_validation_service import verify_execution_equivalence
    try:
        verdict = verify_execution_equivalence(original, edited)
    except Exception:
        return "not_verified"
    if not isinstance(verdict, dict):
        return "not_verified"
    if verdict.get("status") == "equivalent" and verdict.get("equivalent") is True:
        return "equivalent"
    if verdict.get("status") == "different" and verdict.get("equivalent") is False:
        return "different"
    return "not_verified"


def _percentage(numerator: int, denominator: int) -> float | None:
    return round(100 * numerator / denominator, 2) if denominator else None


def audit(*, runtime_limit: int = 0) -> dict:
    """Return JSON-safe counts. No raw fixture code enters the report."""
    if type(runtime_limit) is not int or not 0 <= runtime_limit <= 30:
        raise ValueError("runtime_limit must be an integer in 0..30")
    baseline = previous.audit()
    s = baseline["summary"]
    issue_list = list(s.get("audit_issues", [])) + list(s.get("registry_issues", []))
    rows = []
    case_count = case_passed = edited_cases = unobserved_cases = 0
    changed_calls = unchanged_calls = invalid_calls = 0
    tagged_edits = applied_tags = 0
    runtime_used = 0
    runtime_counts = {"equivalent": 0, "different": 0, "not_verified": 0, "not_run": 0}

    for base_row in baseline["tags"]:
        tag = base_row["tag"]
        action = base_row.get("action")
        transformer = _get_transform_function(action) if type(action) is str else None
        case_details = []
        samples = []
        for case in base_row.get("cases", []):
            test_id = case.get("test")
            if not isinstance(test_id, str):
                continue
            case_count += 1
            if not callable(transformer):
                issue_list.append(f"{tag}: {action} dispatcher missing")
                case_details.append({"level": case.get("level"), "test": test_id,
                                     "passed": False, "observed": "dispatcher_missing"})
                continue
            ok, diagnostic, trace = trace_representative_case(test_id, transformer)
            case_passed += int(ok)
            changed_calls += trace.changed
            unchanged_calls += trace.unchanged
            invalid_calls += trace.invalid
            edited = ok and trace.changed > 0 and trace.invalid == 0
            if edited:
                edited_cases += 1
            elif trace.calls == 0:
                unobserved_cases += 1
            if trace.sample is not None and ok and trace.invalid == 0:
                samples.append(trace.sample)
            if not ok:
                issue_list.append(f"{tag} {test_id}: {diagnostic[-400:]}")
            if trace.invalid:
                issue_list.append(f"{tag} {test_id}: transformer produced invalid Python")
            case_details.append({
                "level": case.get("level"), "test": test_id, "passed": ok,
                "transform_calls": trace.calls, "code_edits": trace.changed,
                "unchanged_returns": trace.unchanged, "invalid_python": trace.invalid,
                "non_string_returns": trace.non_string,
                "observed": ("edited" if edited else "not_seen" if trace.calls == 0
                             else "invalid_python" if trace.invalid
                             else "unchanged_or_inconclusive"),
            })

        has_edit = any(c["observed"] == "edited" for c in case_details)
        tagged_edits += int(has_edit)
        apply_status = "no_observed_example"
        if samples:
            apply_status = check_apply_action(tag, action, samples[0][0])
        applied_tags += int(apply_status == "applied")
        if samples and apply_status != "applied":
            issue_list.append(f"{tag}: observed edit but production applicator returned {apply_status}")
        runtime_status = "not_run"
        if runtime_used < runtime_limit and samples:
            runtime_status = _runtime_classify(*samples[0])
            runtime_used += 1
            if runtime_status == "different":
                issue_list.append(f"{tag}: trusted runtime fixture has a behavior difference")
        runtime_counts[runtime_status] += 1
        rows.append({
            "tag": tag, "action": action, "representative_cases": len(case_details),
            "observed_edit": has_edit, "application_status": apply_status,
            "runtime_verification": runtime_status, "cases": case_details,
        })

    summary = {
        "tags": len(rows), "linked": len(CREATE_ACTION_BY_TAG),
        "baseline_representative_tests": s.get("representative_tests"),
        "baseline_representative_passed": s.get("representative_tests_passed"),
        "replayed_cases": case_count, "replayed_passed": case_passed,
        "edited_cases": edited_cases, "edited_case_rate_percent": _percentage(edited_cases, case_count),
        "unobserved_cases": unobserved_cases,
        "tags_with_observed_edit": tagged_edits,
        "tags_without_observed_edit": [row["tag"] for row in rows if not row["observed_edit"]],
        "tag_observation_rate_percent": _percentage(tagged_edits, len(rows)),
        "tags_with_applied_ledger": applied_tags,
        "observed_calls_changed": changed_calls,
        "observed_calls_unchanged": unchanged_calls,
        "observed_calls_invalid_python": invalid_calls,
        "runtime_verification": runtime_counts,
        "runtime_fixture_limit": runtime_limit,
        "issues": len(issue_list),
    }
    # This audit does NOT interpret absence of instrumentation as a failed edit.
    return {"summary": summary, "tags": rows, "issues": issue_list,
            "methodology": {
                "denominator": "306 named trusted repository representative tests, not arbitrary programs",
                "observed_edit": "exact mapped Python transformer returned changed, syntactically valid source",
                "applied": "production _apply_style_action reported applied for first observed fixture",
                "unobserved": "test passed, but the mapped transformer call was not observed",
                "runtime": "disabled by default; when enabled uses existing restricted verifier, not a sandbox",
                "limitations": "No claim of semantic equivalence for untested input or arbitrary Python code",
            }}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print full JSON report")
    parser.add_argument("--output", type=Path, help="optional JSON output path")
    parser.add_argument("--runtime-limit", type=int, default=0, metavar="N",
                        help="opt-in: verify at most N bundled fixtures (0..30) via restricted runner")
    args = parser.parse_args()
    try:
        report = audit(runtime_limit=args.runtime_limit)
    except ValueError as exc:
        parser.error(str(exc))
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        s = report["summary"]
        print("=== 32차 102태그 실제 변환 관측·안전성 감사 ===")
        print(f"태그 연결 {s['linked']}/{s['tags']}")
        print(f"31차 대표 테스트 {s['baseline_representative_passed']}/{s['baseline_representative_tests']}")
        print(f"대표 테스트 재실행 {s['replayed_passed']}/{s['replayed_cases']}")
        print(f"실제 코드 변경 관측 {s['edited_cases']}/{s['replayed_cases']}개 사례"
              f" ({s['edited_case_rate_percent']}%)")
        print(f"변경 관측 태그 {s['tags_with_observed_edit']}/{s['tags']}개"
              f" ({s['tag_observation_rate_percent']}%)")
        print(f"적용 서비스 applied 관측 태그 {s['tags_with_applied_ledger']}개")
        print(f"관측되지 않은 대표 사례 {s['unobserved_cases']}개 (실패로 단정하지 않음)")
        if s["tags_without_observed_edit"]:
            labels = ", ".join(s["tags_without_observed_edit"][:12])
            more = " ..." if len(s["tags_without_observed_edit"]) > 12 else ""
            print("실제 변경 관측 근거 부족 태그:", labels + more)
        print(f"잘못된 Python 반환 {s['observed_calls_invalid_python']}회")
        if args.runtime_limit:
            print("제한 실행 검증:", s["runtime_verification"])
        else:
            print("실행 동등성: 별도 검증하지 않음 (옵션 --runtime-limit N)")
        print(f"감사 오류 {s['issues']}건")
        for issue in report["issues"][:12]:
            print("검사 오류:", issue)
        if not args.output:
            print("태그별 상세 보고서: --output backend/batch32_audit.json (선택)")
    s = report["summary"]
    return 0 if (
        s["issues"] == 0 and s["tags"] == s["linked"] == 102
        and s["baseline_representative_passed"] == s["baseline_representative_tests"] == 306
        and s["replayed_passed"] == s["replayed_cases"] == 306
        and s["observed_calls_invalid_python"] == 0
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
