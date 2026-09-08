import libcst as cst


class FunctionStructureTransformer(cst.CSTTransformer):
    """
    함수 중심 코드 구조 변환기.

    목표:
    - 저장된 스타일이 함수 중심 구조를 가지고 있고,
      대상 코드가 절차형 실행문 중심일 때 최상위 실행문을 main 함수로 감쌉니다.
    - import문, 기존 함수 정의, 기존 클래스 정의는 최상위에 유지합니다.
    """

    def leave_Module(
        self,
        original_node: cst.Module,
        updated_node: cst.Module,
    ) -> cst.Module:
        if self._has_main_function(updated_node):
            return updated_node

        preserved_body = []
        executable_body = []

        for stmt in updated_node.body:
            if self._should_preserve_top_level(stmt):
                preserved_body.append(stmt)
            else:
                executable_body.append(stmt)

        if not executable_body:
            return updated_node

        main_function = cst.FunctionDef(
            name=cst.Name("main"),
            params=cst.Parameters(),
            body=cst.IndentedBlock(body=executable_body),
        )

        main_guard = cst.parse_statement(
            'if __name__ == "__main__":\n'
            "    main()\n"
        )

        return updated_node.with_changes(
            body=[
                *preserved_body,
                cst.EmptyLine(),
                main_function,
                cst.EmptyLine(),
                main_guard,
            ]
        )

    def _should_preserve_top_level(self, stmt: cst.CSTNode) -> bool:
        if isinstance(stmt, (cst.FunctionDef, cst.ClassDef)):
            return True

        if isinstance(stmt, cst.SimpleStatementLine):
            if not stmt.body:
                return True

            first = stmt.body[0]

            if isinstance(first, (cst.Import, cst.ImportFrom)):
                return True

        return False

    def _has_main_function(self, module: cst.Module) -> bool:
        for stmt in module.body:
            if isinstance(stmt, cst.FunctionDef) and stmt.name.value == "main":
                return True

        return False


def transform_function_style(code: str) -> str:
    try:
        module = cst.parse_module(code)
        transformed = module.visit(FunctionStructureTransformer())
        return transformed.code

    except Exception:
        return code