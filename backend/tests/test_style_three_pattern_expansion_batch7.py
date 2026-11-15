"""Batch 7: positive basic/additional/complex examples for existing actions.

Tests operate on fixed, trusted short Python snippets only. A successful case
must change the AST, compile, and preserve observed stdout/stderr/exit status.
A pass is evidence for the specific shape, not arbitrary Python equivalence.
"""
from __future__ import annotations

import ast
import subprocess
import sys
import unittest

from app.services.improvement.aggregation_style_service import (
    transform_to_sum_aggregation_style,
    transform_to_loop_aggregation_style,
)
from app.services.improvement.mapping_style_service import transform_mapping_style
from app.services.improvement.resource_style_service import transform_resource_style
from app.services.improvement.conditional_return_service import (
    transform_to_if_statement_style,
    transform_to_conditional_expression_style,
    transform_to_boolean_return_style,
)
from app.services.improvement.collection_style_service import (
    transform_to_append_collection_style,
    transform_to_comprehension_collection_style,
)


def _observe(src: str) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, "-I", "-c", src], capture_output=True,
        text=True, timeout=3, check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _assert_positive(test: unittest.TestCase, source: str, transform, marker: str) -> None:
    """Require actual syntax change and identical observed successful execution."""
    updated = transform(source)
    test.assertNotEqual(updated, source, "변환기가 원본을 변경하지 않았습니다")
    test.assertIn(marker, updated)
    before_ast = ast.dump(ast.parse(source), include_attributes=False)
    after_ast = ast.dump(ast.parse(updated), include_attributes=False)
    test.assertNotEqual(before_ast, after_ast, "서식 변경뿐이고 AST 구조가 동일합니다")
    expected = _observe(source)
    test.assertEqual(expected[0], 0, "원본 고정 예제가 실행되지 않습니다")
    test.assertEqual(_observe(updated), expected, "출력 또는 종료 상태가 달라졌습니다")


# Each row: (source code, expected changed source fragment).
# All source snippets are reviewed, static fixtures; no arbitrary input.
FAMILIES = {
    "SumCreationTriplets": (
        transform_to_sum_aggregation_style,
        (
            ('total = 0\nfor item in [1, 2, 3]:\n    total += item\nprint(total)\n', 'sum('),
            ('value = 0\nfor item in (2, 4, 6):\n    value += item\nprint(value)\n', 'sum('),
            ('def calculate():\n    score = 0\n    for item in [3, 5, 8]:\n        score += item\n    return score\nprint(calculate())\n', 'sum('),
        ),
    ),
    "LoopAggregationTriplets": (
        transform_to_loop_aggregation_style,
        (
            ('total = sum([1, 2, 3])\nprint(total)\n', 'for item in'),
            ('value = sum((2, 4, 6))\nprint(value)\n', 'for item in'),
            ('def calculate():\n    score = sum([3, 5, 8])\n    return score\nprint(calculate())\n', 'for item in'),
        ),
    ),
    "MappingCreationTriplets": (
        transform_mapping_style,
        (
            ('result = {}\nfor x in [1, 2, 3]:\n    result[x] = x * 2\nprint(result)\n', 'for x in'),
            ('result = {}\nfor x in [1, 2, 3, 4]:\n    if x % 2 == 0:\n        result[x] = x + 1\nprint(result)\n', 'if x % 2 == 0'),
            ('def compute():\n    result = {}\n    for key in [1, 2, 3]:\n        if key > 1:\n            result[key] = key * 10\n    return result\nprint(compute())\n', 'for key in'),
        ),
    ),
    "ResourceContextTriplets": (
        transform_resource_style,
        (
            ('import io\ndef open():\n    return io.StringIO("ab")\nf = open()\ntext = f.read()\nf.close()\nprint(text)\n', 'with open() as f:'),
            ('import io\ndef open():\n    return io.StringIO("ab\\ncd")\nf = open()\nfirst = f.readline()\nsecond = f.readline()\nf.close()\nprint(first.strip(), second.strip())\n', 'with open() as f:'),
            ('import io\ndef open():\n    return io.StringIO("42")\ndef fetch():\n    handle = open()\n    text = handle.read()\n    handle.close()\n    return text\nprint(fetch())\n', 'with open() as handle:'),
        ),
    ),
    "IfStatementTriplets": (
        transform_to_if_statement_style,
        (
            ('def choose(flag):\n    answer = 7 if flag else 3\n    return answer\nprint(choose(True), choose(False))\n', 'if flag:'),
            ('def choose(flag):\n    return 7 if flag else 3\nprint(choose(True), choose(False))\n', 'if flag:'),
            ('class Calculator:\n    def choose(self, flag):\n        answer = 9 if flag else 4\n        return answer\nprint(Calculator().choose(True))\n', 'if flag:'),
        ),
    ),
    "TernaryExpressionTriplets": (
        transform_to_conditional_expression_style,
        (
            ('def choose(flag):\n    if flag:\n        value = 7\n    else:\n        value = 3\n    return value\nprint(choose(True), choose(False))\n', ' if (flag) else '),
            ('def choose(flag):\n    if flag:\n        return 7\n    else:\n        return 3\nprint(choose(True), choose(False))\n', ' if (flag) else '),
            ('class Calculator:\n    def choose(self, value):\n        if value > 0:\n            result = value * 2\n        else:\n            result = 0\n        return result\nprint(Calculator().choose(5))\n', ' if (value > 0) else '),
        ),
    ),
    "ReturnStructureTriplets": (
        transform_to_boolean_return_style,
        (
            ('def active(flag):\n    if flag:\n        return True\n    else:\n        return False\nprint(active(9), active(0))\n', 'return not not (flag)'),
            ('def inactive(flag):\n    if flag:\n        return False\n    else:\n        return True\nprint(inactive(9), inactive(0))\n', 'return not (flag)'),
            ('class Validator:\n    def check(self, value):\n        if value > 0:\n            return True\n        else:\n            return False\nprint(Validator().check(5), Validator().check(-1))\n', 'return not not (value > 0)'),
        ),
    ),
    "BroadComprehensionTriplets": (
        transform_to_comprehension_collection_style,
        (
            ('result = []\nfor x in [1, 2, 3]:\n    result.append(x * 2)\nprint(result)\n', 'for x in'),
            ('result = []\nfor x in [1, 2, 3, 4]:\n    if x > 2:\n        result.append(x + 1)\nprint(result)\n', 'if x > 2'),
            ('def calculate():\n    result = []\n    for x in [1, 2, 3]:\n        if x % 2:\n            result.append(x * x)\n    return result\nprint(calculate())\n', 'for x in'),
        ),
    ),
    "AppendExpansionTriplets": (
        transform_to_append_collection_style,
        (
            ('result = [x * 2 for x in [1, 2, 3]]\nprint(result)\n', 'result.append('),
            ('result = [x for x in [1, 2, 3, 4] if x > 2]\nprint(result)\n', 'result.append('),
            ('def calculate():\n    values = [x * 3 for x in [1, 2, 3] if x % 2]\n    return values\nprint(calculate())\n', 'values.append('),
        ),
    ),
}


def _new_test(func, source: str, marker: str):
    def check(self):
        _assert_positive(self, source, func, marker)
    return check


for _name, (_func, _examples) in FAMILIES.items():
    _members = {'__module__': __name__}
    for _level, (_source, _marker) in zip(('basic', 'additional', 'complex'), _examples):
        _members[f'test_{_level}'] = _new_test(_func, _source, _marker)
    globals()[_name] = type(_name, (unittest.TestCase,), _members)


if __name__ == '__main__':
    unittest.main()
