
from fastapi import APIRouter

from app.schemas.style_apply import (
    StyleApplyRequest,
    StyleApplyResponse,
)
from app.services.style_apply_service import apply_coding_style
from app.services.style_format_apply_service import apply_saved_formatting_style
from app.services.execution_validation_service import verify_execution_equivalence


router = APIRouter()


@router.post(
    "/apply-style",
    response_model=StyleApplyResponse,
)
def apply_style_api(request: StyleApplyRequest):
    """
    저장된 코딩 스타일을 대상 Python 코드에 적용합니다.

    function_cases가 전달되지 않으면:
        기존 실행 결과 비교만 수행합니다.

    function_cases가 전달되면:
        기존 실행 결과 비교와 함께
        지정된 함수의 반환값 및 자료형도 검증합니다.

    실행 결과에 차이가 발견되면 style_apply_service에서
    변환을 취소하고 원본 코드를 유지합니다.
    """

    if request.language.lower() != "python":
        return StyleApplyResponse(
            success=False,
            original_code=request.code,
            transformed_code="",
            final_analysis=None,
            missing_syntax_tags=[],
            missing_concept_tags=[],
            execution_verification=None,
            applied_rules=[],
            warnings=[],
            error="현재는 Python만 지원합니다.",
        )

    try:
        # 기존 API 요청은 function_cases가 None입니다.
        # 함수 테스트가 전달된 경우에만 딕셔너리 형태로 변환합니다.
        function_cases = (
            [
                case.model_dump()
                for case in request.function_cases
            ]
            if request.function_cases is not None
            else None
        )

        (
            transformed_code,
            summary,
            applied_rules,
            warnings,
            final_diff,
            execution_verification,
        ) = apply_coding_style(
            code=request.code,
            style=request.style.model_dump(),
            function_cases=function_cases,
        )

        # CAPSTONE_SAVED_FORMAT_APPLY_V1: 기존 문법/개념 변환과 실행 검증이 끝난 뒤 서식을 적용합니다.
        # 프로필이 없는 기존 저장 스타일은 기존 동작과 완전히 같습니다.
        # CAPSTONE_FORMATTING_EXECUTION_VERIFY_V2: 서식 변경 전 상태 기록
        code_before_format = transformed_code
        rules_before_format = len(applied_rules)
        summary_before_format = summary
        formatting_profile = request.style.formatting_style
        verification_status = (
            execution_verification.get("status")
            if isinstance(execution_verification, dict)
            else None
        )
        prior_transform_rolled_back = (
            transformed_code == request.code
            and any(
                "전체 변환을 취소" in str(note)
                for note in warnings
            )
        )
        if formatting_profile is not None and not (
            verification_status == "different" or prior_transform_rolled_back
        ):
            formatted_code, format_rules, format_warnings = apply_saved_formatting_style(
                transformed_code, formatting_profile
            )
            if formatted_code != transformed_code:
                transformed_code = formatted_code
                applied_rules.extend(format_rules)
                if execution_verification is None:
                    summary = (summary or "").replace(
                        "최종 코드 변경이 없어 별도의 실행 결과 비교를 수행하지 않았습니다.",
                        "문법/개념 태그 변환으로 인한 구조 변경이 없어 별도의 실행 결과 비교를 수행하지 않았습니다.",
                    )
                summary = (summary or "") + (
                    " 저장된 서식을 최종 코드에 적용했습니다. "
                    "서식은 Python AST 구조 동일성을 확인했으며, "
                    "줄 번호 관찰 등 모든 동작의 동등성을 보증하지 않습니다."
                )
            warnings.extend(format_warnings)
        elif formatting_profile is not None:
            warnings.append(
                "기존 문법/개념 변환이 검증 과정에서 취소되어 서식 적용도 생략했습니다."
            )

        # CAPSTONE_FORMATTING_EXECUTION_VERIFY_V2: 화면에 표시되는 *최종 코드*의 실행 결과를 생성합니다.
        # 기존 서비스는 AST가 동일한 서식 변경만 발생하면 검증을 생략합니다.
        # 원본과 최종 코드를 비교해야 실행 결과 두 칸을 표시할 수 있습니다.
        if formatting_profile is not None and transformed_code != code_before_format:
            try:
                final_check = verify_execution_equivalence(
                    original_code=request.code,
                    transformed_code=transformed_code,
                    function_cases=function_cases,
                )
            except Exception as error:
                final_check = None
                warnings.append(
                    "서식 적용 후 실행 검증기에 오류가 발생했습니다: "
                    + type(error).__name__
                )

            check_valid = isinstance(final_check, dict)
            if check_valid:
                check_status = final_check.get("status")
                equivalent = final_check.get("equivalent")
                check_valid = (
                    check_status in ("equivalent", "different", "not_verified")
                    and type(equivalent) in (bool, type(None))
                    and (check_status != "equivalent" or equivalent is True)
                    and (check_status != "different" or equivalent is False)
                    and (check_status != "not_verified" or equivalent is None)
                    and isinstance(final_check.get("original"), dict)
                    and isinstance(final_check.get("transformed"), dict)
                )

            if not check_valid:
                # Missing/contradictory verification must not silently count
                # as a successful formatting action.  Keep verified tag edits.
                transformed_code = code_before_format
                del applied_rules[rules_before_format:]
                summary = summary_before_format + (
                    " 서식 변경의 실행 검증 결과가 불완전하여 서식만 취소했습니다."
                )
                warnings.append(
                    "서식 적용 후 실행 결과를 검증하지 못해 서식 변경을 취소했습니다."
                )
            elif final_check["status"] == "different":
                # Preserve earlier tag transforms if they had passed their own
                # checks.  Only the newly applied formatting is rolled back.
                transformed_code = code_before_format
                del applied_rules[rules_before_format:]
                summary = summary_before_format + (
                    " 서식 변환 후 실행 결과가 달라 서식 변경을 취소했습니다."
                )
                warnings.append(
                    "서식 적용 전후 실행 결과가 달라 서식 변경을 취소했습니다. "
                    "문법/개념 태그 변환 결과는 기존 검증 판정을 유지합니다."
                )
                if execution_verification is None:
                    # Display why formatting was rejected.  This report is for
                    # the *attempted* formatting, not a successfully changed code.
                    execution_verification = final_check
            else:
                # Recheck the actual displayed result, including optional
                # function cases; pre-format verification would be stale.
                execution_verification = final_check
                summary = summary.replace(
                    "문법/개념 태그 변환으로 인한 구조 변경이 없어 별도의 실행 결과 비교를 수행하지 않았습니다.",
                    "최종 서식 적용 후 원본 코드와 실행 결과를 비교했습니다.",
                ).replace(
                    "최종 코드 변경이 없어 별도의 실행 결과 비교를 수행하지 않았습니다.",
                    "최종 서식 적용 후 원본 코드와 실행 결과를 비교했습니다.",
                )
                if final_check["status"] == "not_verified":
                    warnings.append(
                        "최종 서식 적용 후 실행 동등성을 확인하지 못했습니다. "
                        "화면의 검증 메시지를 확인해 주세요."
                    )

        return StyleApplyResponse(
            success=True,
            original_code=request.code,
            transformed_code=transformed_code,
            final_analysis=final_diff.get("target_analysis"),
            missing_syntax_tags=final_diff.get(
                "missing_syntax_tags",
                [],
            ),
            missing_concept_tags=final_diff.get(
                "missing_concept_tags",
                [],
            ),
            execution_verification=execution_verification,
            summary=summary,
            applied_rules=applied_rules,
            warnings=warnings,
            error=None,
        )

    except SyntaxError as e:
        return StyleApplyResponse(
            success=False,
            original_code=request.code,
            transformed_code="",
            final_analysis=None,
            missing_syntax_tags=[],
            missing_concept_tags=[],
            execution_verification=None,
            applied_rules=[],
            warnings=[],
            error=(
                f"문법 오류: {e.msg} "
                f"(line {e.lineno})"
            ),
        )

    except Exception as e:
        return StyleApplyResponse(
            success=False,
            original_code=request.code,
            transformed_code="",
            final_analysis=None,
            missing_syntax_tags=[],
            missing_concept_tags=[],
            execution_verification=None,
            applied_rules=[],
            warnings=[],
            error=(
                "스타일 적용 중 오류 발생: "
                f"{str(e)}"
            ),
        )
