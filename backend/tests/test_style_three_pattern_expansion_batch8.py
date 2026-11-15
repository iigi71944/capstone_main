"""Batch 8: three positive shapes for each remaining linked tag family.

The 21 positive cases require an actual AST change, valid Python, successful
execution, and matching stdout/stderr/return code. All snippets are fixed,
short, reviewed demonstration fixtures. Seven negative tests check fail-closed
behavior. This does not prove equivalence for arbitrary programs.
"""
from __future__ import annotations

import ast
import subprocess
import sys
import unittest

from app.services.improvement.string_style_service import (
    transform_string_style,
    transform_to_fstring_style,
)
from app.services.improvement.search_style_service import transform_search_style
from app.services.improvement.filter_style_service import transform_to_filter_style
from app.services.improvement.condition_style_service import transform_condition_style
from app.services.improvement.sorting_style_service import transform_to_sort_style
from app.services.improvement.function_style_service import transform_function_style


def _observe(source: str) -> tuple[int, str, str]:
    observed = subprocess.run(
        [sys.executable, '-I', '-c', source],
        capture_output=True, text=True, check=False, timeout=3,
    )
    return observed.returncode, observed.stdout, observed.stderr


def _positive(test: unittest.TestCase, source: str, transform, markers: tuple[str, ...]):
    changed = transform(source)
    test.assertIsInstance(changed, str)
    test.assertNotEqual(changed, source, 'The transformer did not rewrite this example')
    for marker in markers:
        test.assertIn(marker, changed)
    original_ast = ast.dump(ast.parse(source), include_attributes=False)
    changed_ast = ast.dump(ast.parse(changed), include_attributes=False)
    test.assertNotEqual(original_ast, changed_ast, 'Formatting-only changes are not counted')
    before = _observe(source)
    test.assertEqual(before[0], 0, f'Trusted baseline did not execute: {before}')
    test.assertEqual(_observe(changed), before, 'Execution outputs or exit status differ')
    # Re-running a one-way style transformer should not make repeated edits.
    test.assertEqual(transform(changed), changed, 'Transformer is not idempotent')


# Three *distinct supported structural shapes* per transformer family.
# The third is not just a different constant: it uses a function, nested
# function, class method, or multiple code elements.
FAMILIES = {
    'FStringTriplets': (
        transform_to_fstring_style,
        (
            ('name = "Ara"\ntext = "Hello {}".format(name)\nprint(text)\n', ('f"',)),
            ('count = 3\ntext = "Count: {value}".format(value=count)\nprint(text)\n', ('f"',)),
            ('def greet(name):\n    return "Welcome, {}!".format(name)\nprint(greet("Lee"))\n', ('f"',)),
        ),
    ),
    'SearchTriplets': (
        transform_search_style,
        (
            ('def first_even(items):\n    for item in items:\n        if item % 2 == 0:\n            return item\n    return None\nprint(first_even([1, 3, 6]))\n', ('next(',)),
            ('def has_big(items):\n    for x in items:\n        if x > 5:\n            return True\n    return False\nprint(has_big([1, 2, 8]))\n', ('any(',)),
            ('def outer(threshold):\n    def find(items):\n        for item in items:\n            if item >= threshold:\n                return item\n        return None\n    return find([1, 4, 7])\nprint(outer(5))\n', ('next(',)),
        ),
    ),
    'FilterTriplets': (
        transform_to_filter_style,
        (
            ('source = [-1, 0, 2]\nresult = []\nfor x in source:\n    if x > 0:\n        result.append(x)\nprint(result)\n', ('for x in source if x > 0',)),
            ('source = [-2, 1, 4]\nresult = []\nfor x in source:\n    if x > 0 and x < 4:\n        result.append(x * 2)\nprint(result)\n', ('for x in source if',)),
            ('def positives(numbers):\n    kept = []\n    for number in numbers:\n        if number % 2 == 0:\n            kept.append(number + 1)\n    return kept\nprint(positives([1, 2, 3, 4]))\n', ('for number in numbers if',)),
        ),
    ),
    'StringChainTriplets': (
        transform_string_style,
        (
            ('name = "  ArA  "\nname = name.strip()\nname = name.lower()\nprint(name)\n', ('.strip().lower()',)),
            ('text = "  ab  "\ntext = text.strip()\ntext = text.upper()\ntext = text.replace("A", "X")\nprint(text)\n', ('.strip().upper().replace(',)),
            ('def clean(value):\n    value = value.strip()\n    value = value.lower()\n    value = value.replace("a", "b")\n    return value\nprint(clean("  Aaa  "))\n', ('.strip().lower().replace(',)),
        ),
    ),
    'ConditionTriplets': (
        transform_condition_style,
        (
            ('def pick(x):\n    if x > 0:\n        if x < 4:\n            return "small"\n    return "other"\nprint(pick(2), pick(5))\n', ('and',)),
            ('def enabled(value):\n    if value:\n        return True\n    else:\n        return False\nprint(enabled(True), enabled(False))\n', ('return value',)),
            ('class Choice:\n    def choose(self, x):\n        if x > 0:\n            return "yes"\n        else:\n            return "no"\nprint(Choice().choose(1), Choice().choose(-1))\n', ('return \'no\'',)),
        ),
    ),
    'SortTriplets': (
        transform_to_sort_style,
        (
            ('values = [3, 1, 2]\nvalues.sort()\nprint(values)\n', ('sorted(',)),
            ('values = [3, 1, 2]\nvalues.sort(reverse=True)\nprint(values)\n', ('sorted(', 'reverse=True')),
            ('def ordered():\n    words = ["pear", "apple", "fig"]\n    words.sort(reverse=False)\n    return words\nprint(ordered())\n', ('sorted(', 'reverse=False')),
        ),
    ),
    'FunctionStructureTriplets': (
        transform_function_style,
        (
            ('answer = 2 + 3\nprint(answer)\n', ('def main(', 'if __name__')),
            ('import math\nvalue = math.sqrt(16)\nprint(value)\n', ('def main(', 'if __name__', 'import math')),
            ('def triple(value):\n    return value * 3\nresult = triple(4)\nprint(result)\n', ('def triple(', 'def main(', 'if __name__')),
        ),
    ),
}


def _make_positive(transform, source, markers):
    def run(self):
        _positive(self, source, transform, markers)
    return run


for _family_name, (_transform, _examples) in FAMILIES.items():
    _attrs = {'__module__': __name__}
    for _level, (_src, _markers) in zip(('basic', 'additional', 'complex'), _examples):
        _attrs['test_' + _level] = _make_positive(_transform, _src, _markers)
    globals()[_family_name] = type(_family_name, (unittest.TestCase,), _attrs)


class SafeSkipTests(unittest.TestCase):
    """Seven negative cases: unsupported inputs should remain unchanged."""

    def test_fstring_multiple_fields(self):
        source = 'print("{} {}".format(1, 2))\n'
        self.assertEqual(transform_to_fstring_style(source), source)

    def test_search_for_else(self):
        source = 'def f(items):\n    for x in items:\n        if x:\n            return x\n    else:\n        print("end")\n    return None\n'
        self.assertEqual(transform_search_style(source), source)

    def test_filter_comment_inside(self):
        source = 'numbers = [1, 2]\nfound = []\nfor x in numbers:\n    if x > 0:  # keep context\n        found.append(x)\n'
        self.assertEqual(transform_to_filter_style(source), source)

    def test_string_single_call(self):
        source = 'name = " Ab "\nname = name.strip()\n'
        self.assertEqual(transform_string_style(source), source)

    def test_condition_branch_side_effects(self):
        source = 'def f(x):\n    if x:\n        print("yes")\n    else:\n        print("no")\n'
        self.assertEqual(transform_condition_style(source), source)

    def test_sort_builtin_shadowing(self):
        source = 'sorted = lambda x: x\nvalues = [3, 1, 2]\nvalues.sort()\n'
        self.assertEqual(transform_to_sort_style(source), source)

    def test_function_existing_main(self):
        source = 'def main():\n    print("hello")\nmain()\n'
        self.assertEqual(transform_function_style(source), source)


if __name__ == '__main__':
    unittest.main()
