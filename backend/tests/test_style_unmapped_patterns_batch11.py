"""Batch 11 fixed trusted fixtures: rewrite, syntax, runtime, stable output.

Subprocess -I is used only with fixed tests, never user-submitted code.
"""
from __future__ import annotations
import ast
import contextlib
import io
import unittest

from app.services.improvement.safe_unmapped_patterns_batch11_service import (
    transform_to_safe_literal_len_style as length,
    transform_to_safe_literal_zip_style as zipped,
    transform_to_safe_list_slice_style as sliced,
)


def observed(code: str):
    # Run *only* the fixed literal examples below, not external user code.
    output = io.StringIO()
    scope = {}
    with contextlib.redirect_stdout(output):
        try:
            exec(compile(code, '<fixed-batch11-fixture>', 'exec'), scope)
            error = ''
            status = 0
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
            status = 1
    return (status, output.getvalue(), error)


def success(test, source: str, transform, marker: str):
    actual = transform(source)
    test.assertNotEqual(actual, source, 'Must actually rewrite the source')
    test.assertIn(marker, actual)
    test.assertNotEqual(ast.dump(ast.parse(source)), ast.dump(ast.parse(actual)))
    before = observed(source)
    test.assertEqual(before[0], 0, before)
    test.assertEqual(observed(actual), before)
    test.assertEqual(transform(actual), actual, 'Transformation should be idempotent')
    return actual


class LenTriplets(unittest.TestCase):
    def test_basic(self):
        success(self, 'result = sum(1 for x in [2, 5, 8])\nprint(result)\n',
                length, 'len([2, 5, 8])')

    def test_additional(self):
        success(self, 'def count_items():\n    return sum(1 for item in ("가", "나", "다"))\nprint(count_items())\n',
                length, 'len(("가", "나", "다"))')

    def test_complex(self):
        success(self, 'def sizes():\n    a = sum(1 for item in [True, None, 4])\n    b = sum(1 for y in (10, 20, 30, 40))\n    return a, b\nprint(sizes())\n',
                length, 'len((10, 20, 30, 40))')


class ZipTriplets(unittest.TestCase):
    def test_basic(self):
        success(self, 'for a, b in [(1, 2), (3, 4)]:\n    print(a+b)\n',
                zipped, 'zip((1, 3), (2, 4))')

    def test_additional(self):
        success(self, 'pairs = []\nfor key, value in (("a", 2), ("b", 5), ("c", 9)):\n    pairs.append(f"{key}:{value}")\nprint(pairs)\n',
                zipped, 'zip(')

    def test_complex(self):
        success(self, 'def calculate():\n    total = 0\n    for left, right in [[-1, 4], [5, 6], [7, 8], [2, -3]]:\n        if left > 0:\n            total += left * right\n    return total\nprint(calculate())\n',
                zipped, 'zip(')


class SliceTriplets(unittest.TestCase):
    def test_basic(self):
        success(self, 'items = [1, 2, 3]\nresult = items.copy()\nprint(result)\n',
                sliced, 'items[:]')

    def test_additional(self):
        success(self, 'def duplicate():\n    values = ["a", "b", "c"]\n    return values.copy()\nprint(duplicate())\n',
                sliced, 'values[:]')

    def test_complex(self):
        success(self, 'original = [[1], [2]]\ncopy = original.copy()\ncopy[0].append(8)\nprint(original, copy, original is copy)\n',
                sliced, 'original[:]')


class SkipUnsafePatterns(unittest.TestCase):
    def test_len_unknown_iterable(self):
        source = 'def f(data):\n    return sum(1 for x in data)\n'
        self.assertEqual(length(source), source)

    def test_len_filter(self):
        source = 'result = sum(1 for x in [1, 2, 3] if x > 1)\n'
        self.assertEqual(length(source), source)

    def test_len_side_effect(self):
        source = 'result = sum(1 for x in [print("side effect")])\n'
        self.assertEqual(length(source), source)

    def test_len_shadowed(self):
        source = 'len = lambda x: 999\nresult = sum(1 for x in [1,2])\n'
        self.assertEqual(length(source), source)

    def test_sum_shadowed(self):
        source = 'sum = lambda x: 5\nresult = sum(1 for x in [1,2])\n'
        self.assertEqual(length(source), source)

    def test_len_non_counting_generator(self):
        source = 'result = sum(x for x in [1, 2, 3])\n'
        self.assertEqual(length(source), source)

    def test_zip_unknown_pairs(self):
        source = 'pairs = get_pairs()\nfor a,b in pairs:\n    print(a,b)\n'
        self.assertEqual(zipped(source), source)

    def test_zip_mixed_computed_values(self):
        source = 'for a,b in [(1, 2), (get_value(), 4)]:\n    print(a,b)\n'
        self.assertEqual(zipped(source), source)

    def test_zip_shadowed(self):
        source = 'zip = lambda a,b: []\nfor a,b in [(1, 2), (3, 4)]:\n    print(a,b)\n'
        self.assertEqual(zipped(source), source)

    def test_zip_no_assignment_pairs(self):
        source = 'for pair in [(1,2),(3,4)]:\n    print(pair)\n'
        self.assertEqual(zipped(source), source)

    def test_slice_custom_object(self):
        source = 'class A:\n    def copy(self):\n        return 1\na=A()\nresult=a.copy()\n'
        self.assertEqual(sliced(source), source)

    def test_slice_nonadjacent(self):
        source = 'items=[1,2]\nitems.append(3)\nresult=items.copy()\n'
        self.assertEqual(sliced(source), source)

    def test_slice_non_list(self):
        source = 'items=(1,2)\nresult=items.copy()\n'
        self.assertEqual(sliced(source), source)

    def test_comments_preserved(self):
        source = '# keep\nitems = [1,2] # fine\nresult = items.copy() # outside\n'
        changed = sliced(source)
        self.assertIn('# keep', changed)
        self.assertIn('items[:] # outside', changed)
        self.assertEqual(observed(changed), observed(source))

    def test_comments_within_edit_are_skipped(self):
        source = 'items = [1,2]\nresult = items.copy(\n    # not allowed\n)\n'
        self.assertEqual(sliced(source), source)

    def test_unicode_and_crlf(self):
        source = '값 = ["가", "나"]\r\n복사 = 값.copy()\r\nprint(복사)\r\n'
        changed = success(self, source, sliced, '값[:]')
        self.assertIn('\r\n', changed)

    def test_invalid_source_unchanged(self):
        source = 'def bad(:\n'
        for function in (length, zipped, sliced):
            with self.subTest(transform=function.__name__):
                self.assertEqual(function(source), source)

    def test_dynamic_import_star_skipped(self):
        source = 'from module import *\nresult = sum(1 for x in [1,2])\n'
        self.assertEqual(length(source), source)
        source = 'from module import *\nfor a,b in [(1,2),(3,4)]:\n    print(a,b)\n'
        self.assertEqual(zipped(source), source)

    def test_fixed_literal_matrix(self):
        for n in range(2, 10):
            seq = list(range(n))
            src_len = f'result = sum(1 for item in {seq!r})\nprint(result)\n'
            success(self, src_len, length, 'len(')
            rows = [(x, x*3) for x in seq]
            src_zip = f'for x,y in {rows!r}:\n    print(x + y)\n'
            success(self, src_zip, zipped, 'zip(')


if __name__ == '__main__':
    unittest.main()
