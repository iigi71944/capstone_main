"""Batch 10 basic/additional/complex successes and fail-closed checks.

Fixed short fixtures only. subprocess comparison is not a secure sandbox or a
proof of semantic equivalence for arbitrary user code.
"""
import ast
import subprocess
import sys
import unittest

from app.services.improvement.safe_unmapped_patterns_batch10_service import (
    transform_to_safe_augassign_style as augassign,
    transform_to_safe_enumerate_style as enumerate_style,
)
from app.services.improvement.safe_structural_patterns_service import (
    transform_positional_to_keyword_call as keyword_call,
)
from app.services.improvement.safe_architecture_patterns_service import (
    transform_extract_validation_helper as validation_helper,
)
def direct_return(source):
    from app.services.improvement.conditional_return_service import transform_to_boolean_return_style
    return transform_to_boolean_return_style(source)


def observe(code):
    result = subprocess.run([sys.executable, '-I', '-c', code],
                            capture_output=True, text=True, timeout=5, check=False)
    return result.returncode, result.stdout, result.stderr


def success(test, source, transform, fragment):
    changed = transform(source)
    test.assertNotEqual(source, changed, 'Actual code rewrite is required')
    test.assertNotEqual(ast.dump(ast.parse(source)), ast.dump(ast.parse(changed)))
    test.assertIn(fragment, changed)
    before = observe(source)
    test.assertEqual(before[0], 0, before)
    test.assertEqual(observe(changed), before)
    test.assertEqual(transform(changed), changed, 'Expected stable repeated conversion')
    return changed


class AugassignTriplets(unittest.TestCase):
    def test_basic(self):
        success(self, 'count = 10\ncount = count + 2\nprint(count)\n',
                augassign, 'count += 2')

    def test_additional(self):
        success(self, 'balance = -4\nbalance = balance - 6\nprint(balance)\n',
                augassign, 'balance -= 6')

    def test_complex(self):
        success(self, 'def compute():\n    total = 5\n    total = total * -3\n    return total\nprint(compute())\n',
                augassign, 'total *= -3')


class EnumerateTriplets(unittest.TestCase):
    def test_basic(self):
        success(self, 'items = [2, 4, 6]\nfor i in range(len(items)):\n    print(items[i])\n',
                enumerate_style, 'for i, __capstone_item in enumerate(items):')

    def test_additional(self):
        success(self, 'items = (4, 5, 6)\nresults = []\nfor index in range(len(items)):\n    results.append(items[index] * 3)\nprint(results)\n',
                enumerate_style, 'enumerate(items)')

    def test_complex(self):
        success(self, 'items = [1, -2, 3, -4]\nresults = []\nfor n in range(len(items)):\n    if items[n] > 0:\n        results.append((n, items[n] * items[n]))\nprint(results)\n',
                enumerate_style, 'if __capstone_item > 0:')


class KeywordTriplets(unittest.TestCase):
    def test_basic(self):
        success(self, 'def add(a,b):\n    return a+b\nresult=add(2,3)\nprint(result)\n',
                keyword_call, 'add(a=2, b=3)')

    def test_additional(self):
        success(self, 'def repeat(word, times):\n    return word * times\nresult=repeat("a", 3)\nprint(result)\n',
                keyword_call, 'repeat(word=')

    def test_complex(self):
        success(self, 'def measure(a,b,multiplier):\n    return (a+b)*multiplier\nresult=measure(3,4,2)\nprint(result)\n',
                keyword_call, 'measure(a=3, b=4, multiplier=2)')


class ValidationTriplets(unittest.TestCase):
    def test_basic(self):
        success(self, 'def twice(x):\n    if x < 0:\n        raise ValueError("negative")\n    return x * 2\nprint(twice(4))\n',
                validation_helper, '__capstone_validate_x')

    def test_additional(self):
        success(self, 'def score(value):\n    if value >= 10:\n        raise ValueError("high")\n    return value + 3\nprint(score(5))\n',
                validation_helper, '__capstone_validate_value')

    def test_complex(self):
        success(self, 'def evaluate(n):\n    if n == 0:\n        raise TypeError("zero")\n    return n * n + 5\nprint(evaluate(3))\n',
                validation_helper, '__capstone_validate_n')


class ReturnTriplets(unittest.TestCase):
    def test_basic(self):
        success(self, 'def allowed(x):\n    if x:\n        return True\n    else:\n        return False\nprint(allowed(0), allowed(3))\n',
                direct_return, 'return not not (x)')

    def test_additional(self):
        success(self, 'def blocked(x):\n    if x:\n        return False\n    else:\n        return True\nprint(blocked(1), blocked(0))\n',
                direct_return, 'return not (x)')

    def test_complex(self):
        success(self, 'def valid(x, maximum):\n    if x > 0 and x < maximum:\n        return True\n    else:\n        return False\nprint(valid(3, 10), valid(12, 10), valid(-2, 10))\n',
                direct_return, 'return not not (x > 0 and x < maximum)')


class SkipUnsafeCases(unittest.TestCase):
    def test_augassign_unknown_variable(self):
        code = 'x = get_number()\nx = x + 2\n'
        self.assertEqual(augassign(code), code)

    def test_augassign_user_objects(self):
        code = 'x = [1]\nx = x + [2]\n'
        self.assertEqual(augassign(code), code)

    def test_augassign_nonadjacent(self):
        code = 'x = 2\nprint(x)\nx = x + 3\n'
        self.assertEqual(augassign(code), code)

    def test_augassign_global(self):
        code = 'x = 4\ndef f():\n    global x\n    x = 4\n    x = x + 2\n'
        self.assertEqual(augassign(code), code)

    def test_enumerate_unknown_iterable(self):
        code = 'def f(items):\n    for i in range(len(items)):\n        print(items[i])\n'
        self.assertEqual(enumerate_style(code), code)

    def test_enumerate_mutates_iterable(self):
        code = 'items = [1,2]\nfor i in range(len(items)):\n    items.append(items[i])\n'
        self.assertEqual(enumerate_style(code), code)

    def test_enumerate_shadowed_enumerate(self):
        code = 'enumerate = lambda x: []\nitems = [1,2]\nfor i in range(len(items)):\n    print(items[i])\n'
        self.assertEqual(enumerate_style(code), code)

    def test_enumerate_custom_call(self):
        code = 'items = [1,2]\nfor i in range(len(items)):\n    unknown(items[i])\n'
        self.assertEqual(enumerate_style(code), code)

    def test_invalid_source_unchanged(self):
        for transform in (augassign, enumerate_style):
            with self.subTest(transform=transform.__name__):
                self.assertEqual(transform('def x(:\n'), 'def x(:\n')

    def test_unicode_source(self):
        success(self, '합계 = 2\n합계 = 합계 + 5\nprint(합계)\n', augassign, '합계 += 5')


if __name__ == '__main__':
    unittest.main()
