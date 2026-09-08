from app.services.improvement.concise_libcst_service import transform_to_concise_with_libcst


def transform_to_concise(code: str) -> str:
    return transform_to_concise_with_libcst(code)