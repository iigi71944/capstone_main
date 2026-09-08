from app.services.improvement.structured_service import transform_to_structured


def transform_condition_style(code: str) -> str:
    """
    조건/반환 중심 스타일 변환기.

    현재는 구조 중심 변환기와 연결합니다.

    지원:
    - if return True/False -> return condition
    - if return False/True -> return not condition
    - 불필요한 else 제거
    - 단순 중첩 if 병합
    """

    return transform_to_structured(code)