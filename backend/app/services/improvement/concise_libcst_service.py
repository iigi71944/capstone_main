import libcst as cst


class ForAppendToComprehensionTransformer(cst.CSTTransformer):
    """
    간결성 중심형 LibCST 변환기.

    목표:
    - 실행 결과가 달라질 가능성이 낮은 반복 누적 구조만 변환합니다.
    - append 기반 리스트 누적 구조를 리스트 컴프리헨션으로 통합합니다.

    지원:
    1. result = [] + for item in items: result.append(item)
    2. result = [] + for item in items: if condition: result.append(item)
    """

    def __init__(self):
        self.changed = False

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:
        body = list(updated_node.body)

        if len(body) < 2:
            return updated_node

        new_body = []
        i = 0

        while i < len(body):
            transformed_stmt = None

            if i + 1 < len(body):
                transformed_stmt = self._try_transform_assign_for_pair(
                    assign_line=body[i],
                    for_stmt=body[i + 1],
                )

            if transformed_stmt is not None:
                new_body.append(transformed_stmt)
                self.changed = True
                i += 2
                continue

            new_body.append(body[i])
            i += 1

        return updated_node.with_changes(body=new_body)

    def _try_transform_assign_for_pair(self, assign_line, for_stmt):
        if not (
            isinstance(assign_line, cst.SimpleStatementLine)
            and len(assign_line.body) == 1
            and isinstance(assign_line.body[0], cst.Assign)
        ):
            return None

        assign_stmt = assign_line.body[0]

        if not (
            len(assign_stmt.targets) == 1
            and isinstance(assign_stmt.targets[0].target, cst.Name)
            and isinstance(assign_stmt.value, cst.List)
            and len(assign_stmt.value.elements) == 0
        ):
            return None

        if not isinstance(for_stmt, cst.For):
            return None

        target_name = assign_stmt.targets[0].target.value
        loop_target = for_stmt.target
        loop_iter = for_stmt.iter

        if not isinstance(for_stmt.body, cst.IndentedBlock):
            return None

        loop_body = for_stmt.body.body

        append_value, condition = self._extract_append_from_loop_body(
            loop_body=loop_body,
            target_name=target_name,
        )

        if append_value is None:
            return None

        comp_for = cst.CompFor(
            target=loop_target,
            iter=loop_iter,
            ifs=[cst.CompIf(test=condition)] if condition is not None else [],
        )

        list_comp = cst.ListComp(
            elt=append_value,
            for_in=comp_for,
        )

        return cst.SimpleStatementLine(
            body=[
                cst.Assign(
                    targets=[
                        cst.AssignTarget(
                            target=cst.Name(target_name)
                        )
                    ],
                    value=list_comp,
                )
            ]
        )

    def _extract_append_from_loop_body(self, loop_body, target_name: str):
        if len(loop_body) != 1:
            return None, None

        only_stmt = loop_body[0]

        if isinstance(only_stmt, cst.If):
            if not isinstance(only_stmt.body, cst.IndentedBlock):
                return None, None

            if_body = only_stmt.body.body

            if len(if_body) != 1:
                return None, None

            append_value = self._extract_append_value(
                stmt=if_body[0],
                target_name=target_name,
            )

            if append_value is None:
                return None, None

            return append_value, only_stmt.test

        append_value = self._extract_append_value(
            stmt=only_stmt,
            target_name=target_name,
        )

        return append_value, None

    def _extract_append_value(self, stmt, target_name: str):
        if not (
            isinstance(stmt, cst.SimpleStatementLine)
            and len(stmt.body) == 1
            and isinstance(stmt.body[0], cst.Expr)
            and isinstance(stmt.body[0].value, cst.Call)
        ):
            return None

        call = stmt.body[0].value

        if not (
            isinstance(call.func, cst.Attribute)
            and isinstance(call.func.value, cst.Name)
            and call.func.value.value == target_name
            and isinstance(call.func.attr, cst.Name)
            and call.func.attr.value == "append"
            and len(call.args) == 1
        ):
            return None

        return call.args[0].value


def transform_to_concise_with_libcst(code: str) -> str:
    try:
        module = cst.parse_module(code)
        transformer = ForAppendToComprehensionTransformer()
        transformed = module.visit(transformer)

        if not transformer.changed:
            return code

        return transformed.code

    except Exception:
        return code