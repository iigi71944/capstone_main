import ast


STRING_METHODS = {
    "strip",
    "split",
    "join",
    "replace",
    "lower",
    "upper",
    "startswith",
    "endswith",
    "find",
    "format",
}

LIST_METHODS = {
    "append",
    "extend",
    "insert",
    "remove",
    "pop",
    "sort",
    "reverse",
    "clear",
    "index",
    "count",
}

DICT_METHODS = {
    "get",
    "keys",
    "values",
    "items",
    "update",
    "pop",
    "setdefault",
    "clear",
}


class NestingDepthVisitor(ast.NodeVisitor):
    def __init__(self):
        self.current_depth = 0
        self.max_depth = 0

    def _enter(self):
        self.current_depth += 1
        self.max_depth = max(self.max_depth, self.current_depth)

    def _leave(self):
        self.current_depth -= 1

    def visit_If(self, node):
        self._enter()
        self.generic_visit(node)
        self._leave()

    def visit_For(self, node):
        self._enter()
        self.generic_visit(node)
        self._leave()

    def visit_While(self, node):
        self._enter()
        self.generic_visit(node)
        self._leave()

    def visit_Try(self, node):
        self._enter()
        self.generic_visit(node)
        self._leave()

    def visit_With(self, node):
        self._enter()
        self.generic_visit(node)
        self._leave()


def is_index_based_loop(node: ast.For) -> bool:
    target_is_name = isinstance(node.target, ast.Name)
    iter_is_call = isinstance(node.iter, ast.Call)

    if not (target_is_name and iter_is_call):
        return False

    if not isinstance(node.iter.func, ast.Name) or node.iter.func.id != "range":
        return False

    if len(node.iter.args) != 1:
        return False

    first_arg = node.iter.args[0]

    if not isinstance(first_arg, ast.Call):
        return False

    if not isinstance(first_arg.func, ast.Name) or first_arg.func.id != "len":
        return False

    return True


def is_direct_loop(node: ast.For) -> bool:
    return not is_index_based_loop(node)


def get_function_body_length(node: ast.AST) -> int:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return len(node.body)

    return 0


def has_type_hint(node: ast.AST) -> bool:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.returns is not None:
            return True

        for arg in node.args.args:
            if arg.annotation is not None:
                return True

        for arg in node.args.kwonlyargs:
            if arg.annotation is not None:
                return True

        if node.args.vararg and node.args.vararg.annotation is not None:
            return True

        if node.args.kwarg and node.args.kwarg.annotation is not None:
            return True

    if isinstance(node, ast.AnnAssign):
        return True

    return False


def calculate_metrics(tree: ast.AST) -> dict:
    function_count = 0
    async_function_count = 0
    class_count = 0
    loop_count = 0
    if_count = 0
    return_count = 0
    comprehension_count = 0
    index_loop_count = 0
    direct_loop_count = 0
    append_call_count = 0
    import_count = 0
    assign_count = 0
    aug_assign_count = 0
    call_count = 0
    compare_count = 0
    bool_op_count = 0
    bin_op_count = 0
    break_count = 0
    continue_count = 0
    try_count = 0
    raise_count = 0
    assert_count = 0
    with_count = 0
    lambda_count = 0
    collection_literal_count = 0
    list_literal_count = 0
    dict_literal_count = 0
    tuple_literal_count = 0
    subscript_count = 0
    slicing_count = 0
    attribute_count = 0
    match_count = 0
    decorator_count = 0
    string_literal_count = 0
    number_literal_count = 0
    boolean_literal_count = 0
    none_count = 0
    membership_op_count = 0
    identity_compare_count = 0
    if_exp_count = 0
    positional_arg_count = 0
    keyword_arg_count = 0
    default_param_count = 0
    vararg_count = 0
    kwarg_count = 0
    type_hint_count = 0
    f_string_count = 0
    print_call_count = 0
    input_call_count = 0
    len_call_count = 0
    range_call_count = 0
    sum_call_count = 0
    sorted_call_count = 0
    enumerate_call_count = 0
    zip_call_count = 0
    open_call_count = 0
    string_method_call_count = 0
    list_method_call_count = 0
    dict_method_call_count = 0
    global_count = 0
    await_count = 0
    max_function_body_length = 0
    short_function_count = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            function_count += 1
            decorator_count += len(getattr(node, "decorator_list", []))
            max_function_body_length = max(max_function_body_length, get_function_body_length(node))

            if get_function_body_length(node) <= 5:
                short_function_count += 1

            if has_type_hint(node):
                type_hint_count += 1

            if len(node.args.defaults) > 0 or len(node.args.kw_defaults) > 0:
                default_param_count += 1

            if node.args.vararg is not None:
                vararg_count += 1

            if node.args.kwarg is not None:
                kwarg_count += 1

        if isinstance(node, ast.AsyncFunctionDef):
            function_count += 1
            async_function_count += 1
            decorator_count += len(getattr(node, "decorator_list", []))
            max_function_body_length = max(max_function_body_length, get_function_body_length(node))

            if get_function_body_length(node) <= 5:
                short_function_count += 1

            if has_type_hint(node):
                type_hint_count += 1

            if len(node.args.defaults) > 0 or len(node.args.kw_defaults) > 0:
                default_param_count += 1

            if node.args.vararg is not None:
                vararg_count += 1

            if node.args.kwarg is not None:
                kwarg_count += 1

        if isinstance(node, ast.ClassDef):
            class_count += 1
            decorator_count += len(getattr(node, "decorator_list", []))

        if isinstance(node, (ast.For, ast.While)):
            loop_count += 1

        if isinstance(node, ast.For):
            if is_index_based_loop(node):
                index_loop_count += 1
            elif is_direct_loop(node):
                direct_loop_count += 1

        if isinstance(node, ast.If):
            if_count += 1

        if isinstance(node, ast.Return):
            return_count += 1

        if isinstance(node, (ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp)):
            comprehension_count += 1

        if isinstance(node, (ast.Import, ast.ImportFrom)):
            import_count += 1

        if isinstance(node, ast.Assign):
            assign_count += 1

        if isinstance(node, ast.AnnAssign):
            assign_count += 1
            type_hint_count += 1

        if isinstance(node, ast.AugAssign):
            aug_assign_count += 1

        if isinstance(node, ast.Call):
            call_count += 1

            if isinstance(node.func, ast.Name):
                if node.func.id == "print":
                    print_call_count += 1
                elif node.func.id == "input":
                    input_call_count += 1
                elif node.func.id == "len":
                    len_call_count += 1
                elif node.func.id == "range":
                    range_call_count += 1
                elif node.func.id == "sum":
                    sum_call_count += 1
                elif node.func.id == "sorted":
                    sorted_call_count += 1
                elif node.func.id == "enumerate":
                    enumerate_call_count += 1
                elif node.func.id == "zip":
                    zip_call_count += 1
                elif node.func.id == "open":
                    open_call_count += 1

            if isinstance(node.func, ast.Attribute):
                method_name = node.func.attr

                if method_name == "append":
                    append_call_count += 1

                if method_name in STRING_METHODS:
                    string_method_call_count += 1

                if method_name in LIST_METHODS:
                    list_method_call_count += 1

                if method_name in DICT_METHODS:
                    dict_method_call_count += 1

            positional_arg_count += len(node.args)
            keyword_arg_count += len([keyword for keyword in node.keywords if keyword.arg is not None])

        if isinstance(node, ast.Compare):
            compare_count += 1

            for operator in node.ops:
                if isinstance(operator, (ast.In, ast.NotIn)):
                    membership_op_count += 1

                if isinstance(operator, (ast.Is, ast.IsNot)):
                    identity_compare_count += 1

        if isinstance(node, ast.BoolOp):
            bool_op_count += 1

        if isinstance(node, ast.BinOp):
            bin_op_count += 1

        if isinstance(node, ast.IfExp):
            if_exp_count += 1

        if isinstance(node, ast.Break):
            break_count += 1

        if isinstance(node, ast.Continue):
            continue_count += 1

        if isinstance(node, ast.Try):
            try_count += 1

        if isinstance(node, ast.Raise):
            raise_count += 1

        if isinstance(node, ast.Assert):
            assert_count += 1

        if isinstance(node, ast.With):
            with_count += 1

        if isinstance(node, ast.Lambda):
            lambda_count += 1

        if isinstance(node, ast.List):
            collection_literal_count += 1
            list_literal_count += 1

        if isinstance(node, ast.Dict):
            collection_literal_count += 1
            dict_literal_count += 1

        if isinstance(node, ast.Tuple):
            collection_literal_count += 1
            tuple_literal_count += 1

        if isinstance(node, ast.Set):
            collection_literal_count += 1

        if isinstance(node, ast.Subscript):
            subscript_count += 1
            if isinstance(node.slice, ast.Slice):
                slicing_count += 1

        if isinstance(node, ast.Attribute):
            attribute_count += 1

        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                string_literal_count += 1
            elif isinstance(node.value, bool):
                boolean_literal_count += 1
            elif isinstance(node.value, (int, float, complex)):
                number_literal_count += 1
            elif node.value is None:
                none_count += 1

        if isinstance(node, ast.JoinedStr):
            f_string_count += 1

        if isinstance(node, ast.Global):
            global_count += 1

        if isinstance(node, ast.Await):
            await_count += 1

        if hasattr(ast, "Match") and isinstance(node, ast.Match):
            match_count += 1

    depth_visitor = NestingDepthVisitor()
    depth_visitor.visit(tree)

    return {
        "function_count": function_count,
        "async_function_count": async_function_count,
        "class_count": class_count,
        "loop_count": loop_count,
        "if_count": if_count,
        "return_count": return_count,
        "comprehension_count": comprehension_count,
        "index_loop_count": index_loop_count,
        "direct_loop_count": direct_loop_count,
        "append_call_count": append_call_count,
        "import_count": import_count,
        "assign_count": assign_count,
        "aug_assign_count": aug_assign_count,
        "call_count": call_count,
        "compare_count": compare_count,
        "bool_op_count": bool_op_count,
        "bin_op_count": bin_op_count,
        "break_count": break_count,
        "continue_count": continue_count,
        "try_count": try_count,
        "raise_count": raise_count,
        "assert_count": assert_count,
        "with_count": with_count,
        "lambda_count": lambda_count,
        "collection_literal_count": collection_literal_count,
        "list_literal_count": list_literal_count,
        "dict_literal_count": dict_literal_count,
        "tuple_literal_count": tuple_literal_count,
        "subscript_count": subscript_count,
        "slicing_count": slicing_count,
        "attribute_count": attribute_count,
        "match_count": match_count,
        "decorator_count": decorator_count,
        "string_literal_count": string_literal_count,
        "number_literal_count": number_literal_count,
        "boolean_literal_count": boolean_literal_count,
        "none_count": none_count,
        "membership_op_count": membership_op_count,
        "identity_compare_count": identity_compare_count,
        "if_exp_count": if_exp_count,
        "positional_arg_count": positional_arg_count,
        "keyword_arg_count": keyword_arg_count,
        "default_param_count": default_param_count,
        "vararg_count": vararg_count,
        "kwarg_count": kwarg_count,
        "type_hint_count": type_hint_count,
        "f_string_count": f_string_count,
        "print_call_count": print_call_count,
        "input_call_count": input_call_count,
        "len_call_count": len_call_count,
        "range_call_count": range_call_count,
        "sum_call_count": sum_call_count,
        "sorted_call_count": sorted_call_count,
        "enumerate_call_count": enumerate_call_count,
        "zip_call_count": zip_call_count,
        "open_call_count": open_call_count,
        "string_method_call_count": string_method_call_count,
        "list_method_call_count": list_method_call_count,
        "dict_method_call_count": dict_method_call_count,
        "global_count": global_count,
        "await_count": await_count,
        "max_function_body_length": max_function_body_length,
        "short_function_count": short_function_count,
        "max_nesting_depth": depth_visitor.max_depth,
    }