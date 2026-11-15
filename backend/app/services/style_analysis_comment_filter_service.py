"""분석 전용 AST에서 주석성 문자열을 제외한다.

원본 소스와 AST는 수정하지 않는다. 변환기에는 원본 코드가 그대로 전달된다.
"""

from __future__ import annotations

import ast
import copy


class _RemoveNonExecutableStrings(ast.NodeTransformer):
    """실행문이 아닌 독립적인 문자열 표현식만 제거한다.

    Python 파서는 # 주석을 AST에 넣지 않는다. 독스트링과 흔히 사용되는
    독립적인 삼중 따옴표 '주석'은 Expr(Constant(str))로 들어온다.
    """

    def visit_Expr(self, node: ast.Expr):
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return None
        return self.generic_visit(node)


def without_analysis_comments(tree: ast.AST) -> ast.AST:
    """스타일 분석용 AST를 반환한다. 원본은 그대로 유지한다.

    - # 주석: ast.parse가 이미 제거함
    - 독스트링·독립 문자열 표현식: 분석용 복사본에서 제거
    - 대입/반환/인수로 사용되는 실제 문자열: 유지
    - type: ignore / # type: ... 형태의 타입 주석 메타데이터: 제외
    """
    if not isinstance(tree, ast.AST):
        raise TypeError("Python AST가 필요합니다.")

    analyzed = copy.deepcopy(tree)
    analyzed = _RemoveNonExecutableStrings().visit(analyzed)

    if isinstance(analyzed, ast.Module):
        analyzed.type_ignores = []

    for node in ast.walk(analyzed):
        if hasattr(node, "type_comment"):
            node.type_comment = None

        # 문장 목록에 있던 독스트링만 빠져 빈 본문이 되었을 때에도
        # 분석 트리를 구문적으로 올바르게 유지한다.
        if not isinstance(node, ast.Module) and hasattr(node, "body"):
            body = node.body
            if isinstance(body, list) and not body:
                placeholder = ast.Pass()
                if hasattr(node, "lineno"):
                    ast.copy_location(placeholder, node)
                node.body = [placeholder]

    return ast.fix_missing_locations(analyzed)
