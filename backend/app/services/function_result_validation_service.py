
"""Run explicit function test cases using the existing Python execution service.

The checker compares values of supported built-in types and observed output for
specified inputs. It does not prove equivalence for other inputs or state.
Do not run untrusted code without a genuine security sandbox.
"""

import json
import keyword
import math
import uuid

# CAPSTONE_BATCH25_FUNCTION_TYPE_GUARD_IMPORT_V1
from app.services.function_input_type_guard_service import validate_function_test_case

from app.services.execution_validation_service import (
    execute_python_code, valid_stdin_input,
)


MAX_CASES = 8
MAX_NESTING = 6
MAX_COLLECTION_LENGTH = 50


def _valid_literal(value, depth: int = 0) -> bool:
    if depth > MAX_NESTING:
        return False

    if value is None or type(value) in (bool, int, str):
        return True

    if type(value) is float:
        return math.isfinite(value)

    if type(value) in (list, tuple):
        return (
            len(value) <= MAX_COLLECTION_LENGTH
            and all(_valid_literal(item, depth + 1) for item in value)
        )

    if type(value) is dict:
        return (
            len(value) <= MAX_COLLECTION_LENGTH
            and all(
                type(key) is str and _valid_literal(item, depth + 1)
                for key, item in value.items()
            )
        )

    return False


def _validated_case(case: dict) -> tuple[str, list, dict]:
    if not isinstance(case, dict):
        raise ValueError(
            "Each function test case must be a dictionary."
        )

    function_name = case.get("function")
    args = case.get("args", [])
    kwargs = case.get("kwargs", {})

    if not (
        isinstance(function_name, str)
        and function_name.isidentifier()
        and not keyword.iskeyword(function_name)
        and not function_name.startswith("__capstone_")
    ):
        raise ValueError(
            "A test must specify a simple Python function name."
        )

    if not isinstance(args, list) or not isinstance(kwargs, dict):
        raise ValueError(
            "args must be a list and kwargs must be a dictionary."
        )

    if len(args) + len(kwargs) > MAX_COLLECTION_LENGTH:
        raise ValueError("Too many function arguments.")

    if not all(_valid_literal(value) for value in args):
        raise ValueError(
            "Only supported literal function arguments are allowed."
        )

    for name, value in kwargs.items():
        if not (
            isinstance(name, str)
            and name.isidentifier()
            and not keyword.iskeyword(name)
            and _valid_literal(value)
        ):
            raise ValueError(
                "Invalid keyword argument or value."
            )

    case_stdin = case.get("stdin")
    if case_stdin is not None and not valid_stdin_input(case_stdin):
        raise ValueError("Function-test stdin exceeds limits or is not text.")
    return function_name, args, kwargs


def _build_test_program(
    code: str,
    function_name: str,
    args: list,
    kwargs: dict,
    marker: str,
) -> str:
    argument_parts = [
        repr(value)
        for value in args
    ]

    argument_parts.extend(
        f"{name}={value!r}"
        for name, value in kwargs.items()
    )

    call = f"{function_name}({', '.join(argument_parts)})"

    # The original source is not modified.
    # Test code is appended only to the temporary execution copy.
    harness = f'''
import json as __capstone_json

def __capstone_encode(value, depth=0):
    if depth > {MAX_NESTING}:
        raise TypeError("maximum nesting depth exceeded")

    if value is None:
        return {{"type": "NoneType", "value": None}}

    if type(value) in (bool, int, str):
        return {{
            "type": type(value).__name__,
            "value": value,
        }}

    if type(value) is float:
        if not __capstone_math.isfinite(value):
            raise TypeError("nonfinite float is not supported")

        return {{
            "type": "float",
            "value": value,
        }}

    if type(value) in (list, tuple):
        if len(value) > {MAX_COLLECTION_LENGTH}:
            raise TypeError("collection too long")

        return {{
            "type": type(value).__name__,
            "items": [
                __capstone_encode(item, depth + 1)
                for item in value
            ],
        }}

    if type(value) is dict:
        if len(value) > {MAX_COLLECTION_LENGTH}:
            raise TypeError("collection too long")

        if not all(type(key) is str for key in value):
            raise TypeError("dictionary keys must be strings")

        return {{
            "type": "dict",
            "items": {{
                key: __capstone_encode(item, depth + 1)
                for key, item in value.items()
            }},
        }}

    raise TypeError("unsupported return type")


import math as __capstone_math


def __capstone_check():
    try:
        observed = {call}

    except Exception as exc:
        record = {{
            "kind": "exception",
            "type": type(exc).__name__,
            "message": str(exc),
        }}

    else:
        try:
            record = {{
                "kind": "value",
                "value": __capstone_encode(observed),
            }}

        except (TypeError, ValueError) as exc:
            record = {{
                "kind": "unsupported",
                "reason": str(exc),
            }}

    print(
        "\\n{marker}"
        + __capstone_json.dumps(
            record,
            ensure_ascii=True,
            sort_keys=True,
            allow_nan=False,
        )
    )


__capstone_check()
'''

    return code.rstrip() + "\n\n" + harness


def _extract_record(
    output: str,
    marker: str,
) -> tuple[str, dict] | None:
    delimiter = "\n" + marker

    before, found, after = output.rpartition(delimiter)

    if not found:
        return None

    try:
        data = json.loads(after.strip())

    except (ValueError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    if data.get("kind") not in {
        "value",
        "exception",
        "unsupported",
    }:
        return None

    return before, data


def _compare_case(
    original_code: str,
    transformed_code: str,
    case: dict,
    stdin: str | None = None,
) -> dict:
    function_name, args, kwargs = _validated_case(case)

    marker = (
        "__capstone_result_"
        + uuid.uuid4().hex
        + "__"
    )

    original_program = _build_test_program(
        original_code,
        function_name,
        args,
        kwargs,
        marker,
    )

    transformed_program = _build_test_program(
        transformed_code,
        function_name,
        args,
        kwargs,
        marker,
    )

    # CAPSTONE_BATCH17_STDIN_V1: same stdin for both programs; case-specific override.
    actual_stdin = case.get("stdin")
    if actual_stdin is None:
        actual_stdin = stdin
    if actual_stdin is None:
        original = execute_python_code(original_program)
        transformed = execute_python_code(transformed_program)
    else:
        original = execute_python_code(original_program, stdin=actual_stdin)
        transformed = execute_python_code(transformed_program, stdin=actual_stdin)

    item = {
        "function": function_name,
        "args": args,
        "kwargs": kwargs,
        "status": "not_verified",
        "equivalent": None,
        "message": "",
        "original_result": None,
        "transformed_result": None,
        "original_stdout": None,
        "transformed_stdout": None,
    }

    if original.blocked or transformed.blocked:
        item["message"] = (
            "Execution was blocked by the runtime policy."
        )
        return item

    if original.timed_out or transformed.timed_out:
        item["message"] = "A function test timed out."
        return item

    if not original.success or not transformed.success:
        item["message"] = (
            "A function test did not finish successfully."
        )
        return item

    before = _extract_record(
        original.stdout,
        marker,
    )

    after = _extract_record(
        transformed.stdout,
        marker,
    )

    if before is None or after is None:
        item["message"] = (
            "The function test result was missing or truncated."
        )
        return item

    before_stdout, before_record = before
    after_stdout, after_record = after

    # Display the actual observations for the supplied function arguments.
    # Preserve type information (list vs tuple, int vs bool, None, etc.).
    item["original_result"] = before_record
    item["transformed_result"] = after_record
    item["original_stdout"] = before_stdout
    item["transformed_stdout"] = after_stdout

    # Unsupported return objects cannot be compared reliably.
    if (
        before_record["kind"] == "unsupported"
        or after_record["kind"] == "unsupported"
    ):
        item["message"] = (
            "A function returned an unsupported value type."
        )
        return item

    # The same exception does not establish correct behavior.
    if (
        before_record["kind"] == "exception"
        and after_record["kind"] == "exception"
    ):
        if (
            before_record == after_record
            and before_stdout == after_stdout
        ):
            item["message"] = (
                "Both function calls raised the same exception; "
                "not verified."
            )
            return item

    # Compare printed output, standard errors and encoded return values.
    if (
        before_stdout != after_stdout
        or original.stderr != transformed.stderr
        or before_record != after_record
    ):
        item["status"] = "different"
        item["equivalent"] = False
        item["message"] = (
            "The observed outputs or function results differ."
        )
        return item

    item["status"] = "equivalent"
    item["equivalent"] = True
    item["message"] = (
        "Return type, return value, and observed output "
        "matched for this input."
    )

    return item


def verify_function_results(
    original_code: str,
    transformed_code: str,
    cases: list[dict],
    stdin: str | None = None,
) -> dict:
    """
    Execute explicit function test cases for both programs.

    Example test case:
        {
            "function": "calculate",
            "args": [5],
            "kwargs": {},
        }

    Each case is executed in fresh Python processes.
    Only supported literal arguments and return values qualify.

    A matching result proves only that the selected inputs
    produced matching observed results.
    """

    if not isinstance(cases, list) or not (
        1 <= len(cases) <= MAX_CASES
    ):
        raise ValueError(
            f"Provide between 1 and {MAX_CASES} "
            "function test cases."
        )

    if stdin is not None and not valid_stdin_input(stdin):
        raise ValueError("Shared stdin exceeds limits or is not text.")
    # CAPSTONE_BATCH25_FUNCTION_TYPE_GUARD_V1: reject known mismatches
    # before any user code is executed in the test runner.
    for case in cases:
        _validated_case(case)
        validate_function_test_case(original_code, case, stdin=stdin)
        if transformed_code != original_code:
            validate_function_test_case(transformed_code, case, stdin=stdin)

    results = [
        _compare_case(
            original_code,
            transformed_code,
            case,
            **({"stdin": stdin} if stdin is not None else {}),
        )
        for case in cases
    ]

    if any(
        item["status"] == "different"
        for item in results
    ):
        status = "different"
        equivalent = False

    elif any(
        item["status"] == "not_verified"
        for item in results
    ):
        status = "not_verified"
        equivalent = None

    else:
        status = "equivalent"
        equivalent = True

    return {
        "status": status,
        "equivalent": equivalent,
        "cases": results,
        "message": (
            "Only the explicitly supplied function inputs "
            "were checked. Other inputs, global state, "
            "and side effects may differ."
        ),
    }
