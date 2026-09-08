def build_refactor_warnings(refactor_tags: list[str]) -> list[str]:
    warnings = []

    if not refactor_tags:
        return warnings

    if "객체 접근 중심 구조" in refactor_tags:
        warnings.append(
            "객체 접근 중심 구조는 자동 변환보다 클래스 구조, 속성 접근 위치, 메서드 책임 분석이 필요하므로 현재는 리팩토링 안내 대상으로 분류했습니다."
        )

    if "중복 로직 포함 구조" in refactor_tags:
        warnings.append(
            "중복 로직 포함 구조는 함수 분리 리팩토링이 필요할 수 있으나, 실행 결과 보존을 위해 현재는 자동 변환하지 않고 안내 대상으로 분류했습니다."
        )

    if "단일 책임 함수 구조" in refactor_tags:
        warnings.append(
            "단일 책임 함수 구조는 이미 좋은 스타일일 수 있으므로 자동 변환 대상이 아니라 스타일 비교 및 유지 기준으로 사용합니다."
        )

    if "함수 호출 중심 구조" in refactor_tags:
        warnings.append(
            "함수 호출 중심 구조는 호출 관계 분석이 필요하므로 현재는 자동 변환보다 구조 안내 대상으로 분류했습니다."
        )

    if "함수 매개변수 활용 구조" in refactor_tags:
        warnings.append(
            "함수 매개변수 활용 구조는 함수 시그니처와 호출부 전체 추적이 필요하므로 현재는 자동 변환하지 않습니다."
        )

    if "클래스 중심 코드 구조" in refactor_tags:
        warnings.append(
            "클래스 중심 코드 구조는 객체 설계 변경이 필요할 수 있어 현재는 자동 변환하지 않고 비교 기준으로 사용합니다."
        )

    if "긴 함수 구조" in refactor_tags:
        warnings.append(
            "긴 함수 구조는 함수 분리 리팩토링 대상이지만, 자동 분리는 실행 흐름을 바꿀 위험이 있어 현재는 안내 대상으로 분류했습니다."
        )

    if "전역 상태 의존 구조" in refactor_tags:
        warnings.append(
            "전역 상태 의존 구조는 매개변수와 반환값 기반 구조로 바꾸는 리팩토링이 필요하지만, 실행 결과 보존을 위해 현재는 자동 변환하지 않습니다."
        )

    return warnings


def build_compare_only_warnings(compare_only_tags: list[str]) -> list[str]:
    if not compare_only_tags:
        return []

    return [
        "다음 태그는 현재 스타일 비교 기준으로 사용되지만, 실행 결과 보존을 위해 자동 변환 규칙은 아직 제한적으로 적용됩니다: "
        + ", ".join(compare_only_tags)
    ]