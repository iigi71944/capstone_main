"""Batch25: typed function args and conservative stdin preflight."""
import unittest

from app.services.function_input_type_guard_service import validate_function_test_case
from app.services.function_result_validation_service import verify_function_results


def check(src, args=None, kwargs=None, stdin=None, name='run'):
    return validate_function_test_case(
        src, {'function': name, 'args': [] if args is None else args,
              'kwargs': {} if kwargs is None else kwargs,
              **({"stdin": stdin} if stdin is not None else {})})


class GuardCases(unittest.TestCase):
    def test_typed_int_success(self):
        check('def run(n: int):\n    return n\n', [5])

    def test_typed_int_str_rejected(self):
        with self.assertRaisesRegex(ValueError, 'int'):
            check('def run(n: int):\n    return n\n', ['5'])

    def test_typed_bool_int_rejected(self):
        with self.assertRaisesRegex(ValueError, 'bool'):
            check('def run(flag: bool):\n    return flag\n', [1])

    def test_typed_float_int_rejected(self):
        with self.assertRaisesRegex(ValueError, 'float'):
            check('def run(n: float):\n    return n\n', [5])

    def test_typed_float_success(self):
        check('def run(n: float):\n    return n\n', [5.0])

    def test_typed_str_kwarg_bad(self):
        with self.assertRaisesRegex(ValueError, 'str'):
            check('def run(name: str):\n    return name\n', kwargs={'name': 1})

    def test_typed_str_kwarg_good(self):
        check('def run(name: str):\n    return name\n', kwargs={'name': 'Lee'})

    def test_untyped_argument_not_guessed(self):
        check('def run(name):\n    return name\n', [3])
        check('def run(name):\n    return name\n', ['Kim'])

    def test_primitive_default_infers_type(self):
        with self.assertRaisesRegex(ValueError, '기본값의 타입 int'):
            check('def run(n=5):\n    return n\n', ['a'])

    def test_default_none_untyped_is_not_inferred(self):
        check('def run(n=None):\n    return n\n', ['a'])

    def test_default_string_infers_type(self):
        with self.assertRaises(ValueError):
            check('def run(label="x"):\n    return label\n', [2])

    def test_list_generic_matches(self):
        check('def run(items: list[int]):\n    return items\n', [[1,2,3]])

    def test_list_generic_mismatch(self):
        with self.assertRaisesRegex(ValueError, r'list\[int\]'):
            check('def run(items: list[int]):\n    return items\n', [[1,'2']])

    def test_list_is_one_argument(self):
        check('def run(items: list):\n    return items\n', [[1,2,3]])

    def test_dict_generic(self):
        check('def run(data: dict[str, int]):\n    return data\n', [{'a': 1}])
        with self.assertRaises(ValueError):
            check('def run(data: dict[str, int]):\n    return data\n', [{'a': '1'}])

    def test_tuple_default(self):
        with self.assertRaises(ValueError):
            check('def run(items=(1,2)):\n    return items\n', [[1,2]])

    def test_optional_none(self):
        check('def run(n: int | None):\n    return n\n', [None])
        check('def run(n: int | None):\n    return n\n', [5])

    def test_optional_wrong(self):
        with self.assertRaises(ValueError):
            check('def run(n: int | None):\n    return n\n', ['5'])

    def test_positional_multiple_mixed_typed(self):
        check('def run(a: int, b: str):\n    return str(a) + b\n', [2,'x'])

    def test_mixed_positional_kw(self):
        check('def run(a: int, b: str):\n    return str(a) + b\n', [2], {'b':'x'})

    def test_kwonly_annotation(self):
        with self.assertRaises(ValueError):
            check('def run(*, flag: bool):\n    return flag\n', kwargs={'flag':0})

    def test_unknown_annotation_keeps_runtime(self):
        check('def run(v: MyCustomType):\n    return v\n', [3])

    def test_stdin_simple_int(self):
        check('def run():\n    n = int(input())\n    return n\n', stdin='123\n')

    def test_stdin_invalid_int(self):
        with self.assertRaisesRegex(ValueError, '1번째.*int'):
            check('def run():\n    n = int(input())\n    return n\n', stdin='hello\n')

    def test_stdin_simple_float(self):
        check('def run():\n    n = float(input())\n    return n\n', stdin='2.25\n')

    def test_stdin_invalid_float(self):
        with self.assertRaisesRegex(ValueError, 'float'):
            check('def run():\n    n = float(input())\n    return n\n', stdin='abc\n')

    def test_stdin_plain_input_is_string(self):
        check('def run():\n    name = input()\n    return name\n', stdin='hello\n')

    def test_stdin_mixed_types_are_valid(self):
        check('def run():\n    a = int(input())\n    b = input()\n    c = float(input())\n    return (a,b,c)\n', stdin='2\nhello\n3.5\n')

    def test_stdin_mixed_second_number_bad(self):
        with self.assertRaisesRegex(ValueError, '2번째.*float'):
            check('def run():\n    a = input()\n    b = float(input())\n    return a,b\n', stdin='hello\nno\n')

    def test_stdin_too_few(self):
        with self.assertRaisesRegex(ValueError, '줄 수가 부족'):
            check('def run():\n    x = input()\n    y = int(input())\n    return x,y\n', stdin='abc\n')

    def test_stdin_shared_fallback(self):
        validate_function_test_case('def run():\n    x = int(input())\n    return x\n',
                                    {'function':'run','args':[], 'kwargs':{}}, stdin='2\n')

    def test_stdin_case_overrides_shared(self):
        validate_function_test_case('def run():\n    x = int(input())\n    return x\n',
                                    {'function':'run','args':[], 'kwargs':{},'stdin':'2\n'},
                                    stdin='no\n')

    def test_stdin_print_wrapped_int_is_checked(self):
        with self.assertRaisesRegex(ValueError, 'int'):
            check('def run():\n    print(int(input()))\n', stdin='wrong\n')

    def test_stdin_return_arithmetic_int_is_checked(self):
        with self.assertRaisesRegex(ValueError, 'int'):
            check('def run():\n    return int(input()) * 2\n', stdin='wrong\n')

    def test_stdin_unknown_prior_call_is_not_guessed(self):
        check('def run():\n    helper()\n    return int(input())\n', stdin='wrong\n')

    def test_stdin_literal_print_before_input(self):
        with self.assertRaisesRegex(ValueError, 'int'):
            check('def run():\n    print("hello")\n    return int(input())\n', stdin='wrong\n')

    def test_rebound_builtin_not_assumed(self):
        check('int = str\ndef run(x: int):\n    return x\n', args=['hello'])

    def test_stdin_return_int(self):
        check('def run():\n    return int(input())\n', stdin='6\n')

    def test_stdin_branch_unpredicted_not_blocked(self):
        check('def run(flag):\n    if flag:\n        return int(input())\n    return 0\n', [False], stdin='abc\n')

    def test_unknown_function_not_guessed(self):
        check('def other(n: int):\n    return n\n', ['x'])

    def test_decorated_function_signature_not_guessed(self):
        check('@wrap\ndef run(n: int):\n    return n\n', ['anything'])

    def test_async_function_execution_not_assumed(self):
        check('async def run():\n    return int(input())\n', stdin='bad\n')

    def test_no_stdin_does_not_preflight(self):
        check('def run():\n    n = int(input())\n    return n\n')

    def test_verify_rejects_bad_typed_argument(self):
        source='def run(x: int):\n    return x\n'
        with self.assertRaisesRegex(ValueError, 'int'):
            verify_function_results(source,source,[{'function':'run','args':['x'],'kwargs':{}}])

    def test_verify_rejects_bad_stdin_before_execution(self):
        source='def run():\n    return int(input())\n'
        with self.assertRaisesRegex(ValueError, 'int'):
            verify_function_results(source,source,[{'function':'run','args':[],'kwargs':{},'stdin':'x\n'}])

    def test_verify_accepts_matching_input(self):
        source='def run(n: int):\n    return n * 2\n'
        report=verify_function_results(source,source,[{'function':'run','args':[2],'kwargs':{}}])
        self.assertEqual(report['status'],'equivalent')


if __name__ == '__main__':
    unittest.main()
