import ast


def parse_code(code: str) -> ast.AST:
    return ast.parse(code)