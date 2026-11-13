"""Existing direct/index for-loop conversions and safe for -> while dispatch.

The direct/index algorithms retain their previous behavior. The former
for-to-while implementation was removed: only for_to_while_service now owns
that conversion, avoiding two competing implementations.
"""

import ast

from app.services.improvement.for_to_while_service import (
    transform_for_to_while_style,
)


class ReplaceIndexWithItem(ast.NodeTransformer):
    def __init__(self, index_name: str, iterable_name: str, item_name: str):
        self.index_name = index_name
        self.iterable_name = iterable_name
        self.item_name = item_name

    def visit_Subscript(self, node: ast.Subscript):
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == self.iterable_name
            and isinstance(node.slice, ast.Name)
            and node.slice.id == self.index_name
        ):
            return ast.Name(id=self.item_name, ctx=ast.Load())
        return self.generic_visit(node)


class ReplaceItemWithIndexAccess(ast.NodeTransformer):
    def __init__(self, item_name: str, iterable_name: str, index_name: str):
        self.item_name = item_name
        self.iterable_name = iterable_name
        self.index_name = index_name

    def visit_Name(self, node: ast.Name):
        if node.id == self.item_name and isinstance(node.ctx, ast.Load):
            return ast.Subscript(
                value=ast.Name(id=self.iterable_name, ctx=ast.Load()),
                slice=ast.Name(id=self.index_name, ctx=ast.Load()),
                ctx=ast.Load(),
            )
        return node


class IterationStyleTransformer(ast.NodeTransformer):
    """Keep the existing direct/index conversion behavior unchanged."""

    def __init__(self, goal: str):
        self.goal = goal
        self.changed = False

    def visit_For(self, node: ast.For):
        self.generic_visit(node)
        if self.goal == "direct":
            result = self._to_direct_iteration(node)
            if result is not None:
                self.changed = True
                return ast.fix_missing_locations(result)
        elif self.goal == "index":
            result = self._to_index_iteration(node)
            if result is not None:
                self.changed = True
                return ast.fix_missing_locations(result)
        return node

    def _to_direct_iteration(self, node: ast.For):
        if not (
            isinstance(node.target, ast.Name)
            and isinstance(node.iter, ast.Call)
            and isinstance(node.iter.func, ast.Name)
            and node.iter.func.id == "range"
            and len(node.iter.args) == 1
            and isinstance(node.iter.args[0], ast.Call)
            and isinstance(node.iter.args[0].func, ast.Name)
            and node.iter.args[0].func.id == "len"
            and len(node.iter.args[0].args) == 1
            and isinstance(node.iter.args[0].args[0], ast.Name)
        ):
            return None

        if node.orelse:
            return None

        index_name = node.target.id
        iterable_name = node.iter.args[0].args[0].id
        item_name = "item"
        replacer = ReplaceIndexWithItem(
            index_name=index_name,
            iterable_name=iterable_name,
            item_name=item_name,
        )
        new_body = [replacer.visit(stmt) for stmt in node.body]
        return ast.For(
            target=ast.Name(id=item_name, ctx=ast.Store()),
            iter=ast.Name(id=iterable_name, ctx=ast.Load()),
            body=new_body,
            orelse=[],
            type_comment=None,
        )

    def _to_index_iteration(self, node: ast.For):
        if not (
            isinstance(node.target, ast.Name)
            and isinstance(node.iter, ast.Name)
        ):
            return None

        if node.orelse:
            return None

        item_name = node.target.id
        iterable_name = node.iter.id
        index_name = "index"
        replacer = ReplaceItemWithIndexAccess(
            item_name=item_name,
            iterable_name=iterable_name,
            index_name=index_name,
        )
        new_body = [replacer.visit(stmt) for stmt in node.body]
        return ast.For(
            target=ast.Name(id=index_name, ctx=ast.Store()),
            iter=ast.Call(
                func=ast.Name(id="range", ctx=ast.Load()),
                args=[
                    ast.Call(
                        func=ast.Name(id="len", ctx=ast.Load()),
                        args=[ast.Name(id=iterable_name, ctx=ast.Load())],
                        keywords=[],
                    )
                ],
                keywords=[],
            ),
            body=new_body,
            orelse=[],
            type_comment=None,
        )


def normalize_code(code: str) -> str:
    try:
        return ast.unparse(ast.parse(code)).strip()
    except Exception:
        return code.strip()


def _transform_iteration(code: str, goal: str) -> str:
    try:
        tree = ast.parse(code)
        transformer = IterationStyleTransformer(goal=goal)
        transformed_tree = transformer.visit(tree)
        ast.fix_missing_locations(transformed_tree)
        if not transformer.changed:
            return code
        transformed_code = ast.unparse(transformed_tree)
        if normalize_code(code) == normalize_code(transformed_code):
            return code
        return transformed_code
    except Exception:
        return code


def transform_to_direct_iteration_style(code: str) -> str:
    return _transform_iteration(code, goal="direct")


def transform_to_index_iteration_style(code: str) -> str:
    return _transform_iteration(code, goal="index")


def transform_to_while_iteration_style(code: str) -> str:
    """Convert general synchronous for-loops using iterator semantics."""
    return transform_for_to_while_style(code)
