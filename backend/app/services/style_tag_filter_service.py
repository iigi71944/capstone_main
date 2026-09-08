STYLE_RELEVANT_SYNTAX_TAGS = {
    "함수 정의",
    "클래스 정의",
    "if문",
    "for문",
    "while문",
    "return문",
    "예외 처리",
    "with문",
    "lambda식",
    "리스트 컴프리헨션",
    "딕셔너리 컴프리헨션",
    "세트 컴프리헨션",
    "제너레이터 표현식",
    "타입 힌트 사용",
    "f-string 사용",
    "비동기 함수 정의",
    "await 사용",
    "패턴 매칭",
    "데코레이터 사용",
}

VALIDATION_RELEVANT_SYNTAX_TAGS = {
    "함수 정의",
    "클래스 정의",
    "if문",
    "for문",
    "while문",
    "return문",
    "예외 처리",
    "with문",
    "lambda식",
    "리스트 컴프리헨션",
    "딕셔너리 컴프리헨션",
    "세트 컴프리헨션",
    "제너레이터 표현식",
    "타입 힌트 사용",
    "비동기 함수 정의",
    "await 사용",
    "패턴 매칭",
    "데코레이터 사용",
}


def filter_style_relevant_syntax_tags(syntax_tags: list[dict]) -> list[dict]:
    return [
        tag for tag in syntax_tags
        if tag.get("tag") in STYLE_RELEVANT_SYNTAX_TAGS
    ]


def filter_validation_relevant_syntax_tags(syntax_tags: list[dict]) -> list[dict]:
    return [
        tag for tag in syntax_tags
        if tag.get("tag") in VALIDATION_RELEVANT_SYNTAX_TAGS
    ]