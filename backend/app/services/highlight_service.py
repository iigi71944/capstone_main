import ast


def extract_highlights(tree: ast.AST) -> list[dict]:
    highlights = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            highlights.append({
                "startLine": getattr(node, "lineno", 1),
                "startColumn": getattr(node, "col_offset", 0) + 1,
                "endLine": getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                "endColumn": getattr(node, "end_col_offset", 1),
                "kind": "function-block",
                "label": "함수 정의",
            })

        elif isinstance(node, ast.For):
            highlights.append({
                "startLine": getattr(node, "lineno", 1),
                "startColumn": getattr(node, "col_offset", 0) + 1,
                "endLine": getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                "endColumn": getattr(node, "end_col_offset", 1),
                "kind": "loop-block",
                "label": "for문",
            })

        elif isinstance(node, ast.While):
            highlights.append({
                "startLine": getattr(node, "lineno", 1),
                "startColumn": getattr(node, "col_offset", 0) + 1,
                "endLine": getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                "endColumn": getattr(node, "end_col_offset", 1),
                "kind": "loop-block",
                "label": "while문",
            })

        elif isinstance(node, ast.If):
            highlights.append({
                "startLine": getattr(node, "lineno", 1),
                "startColumn": getattr(node, "col_offset", 0) + 1,
                "endLine": getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                "endColumn": getattr(node, "end_col_offset", 1),
                "kind": "if-block",
                "label": "if문",
            })

    return highlights