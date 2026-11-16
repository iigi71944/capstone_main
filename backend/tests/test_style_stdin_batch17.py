"""Batch 17: standard input verification and backward-compatibility checks.

Only fixed trusted snippets are executed; untrusted Python is never part of tests.
"""
from __future__ import annotations
import unittest
from unittest.mock import patch

from app.services import execution_validation_service as ev
from app.services.function_result_validation_service import verify_function_results
from app.schemas.style_apply import StyleApplyRequest, CodingStylePayload
from app.api.routes import style_apply as route


class StdinRunnerTests(unittest.TestCase):
    def test_input_without_stdin_is_still_blocked(self):
        r = ev.execute_python_code('print(input("Number: "))')
        self.assertTrue(r.blocked)

    def test_input_with_one_value(self):
        r = ev.execute_python_code('n = int(input("Number: "))\nprint(n * 3)', stdin='5\n')
        self.assertTrue(r.success)
        self.assertEqual(r.stdout, 'Number: 15\n')

    def test_input_with_two_values(self):
        r = ev.execute_python_code('a=int(input())\nb=int(input())\nprint(a+b)', stdin='5\n10\n')
        self.assertTrue(r.success)
        self.assertEqual(r.stdout, '15\n')

    def test_multi_line_and_unicode(self):
        r = ev.execute_python_code('a=input()\nb=input()\nprint(a,b)', stdin='한글\n서울\n')
        self.assertTrue(r.success)
        self.assertEqual(r.stdout, '한글 서울\n')

    def test_input_not_enough_reports_error(self):
        r = ev.execute_python_code('input()\ninput()\nprint(1)', stdin='5\n')
        self.assertFalse(r.success)
        self.assertIn('EOFError', r.stderr)

    def test_input_is_not_code_execution(self):
        r = ev.execute_python_code('print(input())', stdin='__import__("os")\n')
        self.assertTrue(r.success)
        self.assertEqual(r.stdout, '__import__("os")\n')

    def test_open_remains_blocked_with_stdin(self):
        r = ev.execute_python_code('open("file.txt")', stdin='5\n')
        self.assertTrue(r.blocked)

    def test_import_os_remains_blocked_with_stdin(self):
        r = ev.execute_python_code('import os\nprint(input())', stdin='5\n')
        self.assertTrue(r.blocked)

    def test_invalid_stdin_type_is_blocked(self):
        self.assertTrue(ev.execute_python_code('print(1)', stdin=5).blocked)

    def test_stdin_length_limit(self):
        self.assertTrue(ev.execute_python_code('print(1)', stdin='x'*8193).blocked)

    def test_stdin_line_limit(self):
        self.assertTrue(ev.execute_python_code('print(1)', stdin='\n'*129).blocked)

    def test_legacy_simple_print_still_succeeds(self):
        self.assertEqual(ev.execute_python_code('print(1)').stdout, '1\n')

    def test_legacy_run_does_not_send_input_kwarg(self):
        with patch.object(ev.subprocess, 'run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = '1\n'
            run.return_value.stderr = ''
            ev.execute_python_code('print(1)')
        self.assertIn('stdin', run.call_args.kwargs)
        self.assertNotIn('input', run.call_args.kwargs)

    def test_stdin_run_sends_input_kwarg(self):
        with patch.object(ev.subprocess, 'run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = '5\n'
            run.return_value.stderr = ''
            ev.execute_python_code('print(input())', stdin='5\n')
        self.assertEqual(run.call_args.kwargs['input'], '5\n')
        self.assertNotIn('stdin', run.call_args.kwargs)


class VerificationTests(unittest.TestCase):
    def test_same_stdout_with_stdin(self):
        source = 'x=int(input("number?"))\nprint(x*2)\n'
        r = ev.verify_execution_equivalence(source, source, stdin='5\n')
        self.assertEqual(r['status'], 'equivalent')
        self.assertTrue(r['equivalent'])

    def test_different_stdout_with_stdin(self):
        a = 'x=int(input())\nprint(x*2)\n'
        b = 'x=int(input())\nprint(x*3)\n'
        r = ev.verify_execution_equivalence(a, b, stdin='5\n')
        self.assertEqual(r['status'], 'different')

    def test_stdin_not_provided_keeps_policy(self):
        source = 'x=int(input())\nprint(x)'
        r = ev.verify_execution_equivalence(source, source)
        self.assertEqual(r['status'], 'not_verified')

    def test_function_input_shared(self):
        source = 'def calculate():\n    return int(input())*2\n'
        r = ev.verify_execution_equivalence(source, source,
            function_cases=[{'function':'calculate','args':[],'kwargs':{}}], stdin='5\n')
        self.assertEqual(r['status'], 'equivalent')
        self.assertEqual(r['function_verification']['cases'][0]['original_result']['value']['value'], 10)

    def test_function_input_difference(self):
        a = 'def calculate():\n    return int(input())*2\n'
        b = 'def calculate():\n    return int(input())*3\n'
        r = ev.verify_execution_equivalence(a,b,
            function_cases=[{'function':'calculate','args':[],'kwargs':{}}], stdin='5\n')
        self.assertEqual(r['status'], 'different')

    def test_individual_case_input_override(self):
        src = 'def calculate():\n    return int(input())*2\n'
        cases = [{'function':'calculate','args':[],'kwargs':{},'stdin':'5\n'},
                 {'function':'calculate','args':[],'kwargs':{},'stdin':'20\n'}]
        r = verify_function_results(src,src,cases,stdin='9\n')
        self.assertEqual(r['status'],'equivalent')
        self.assertEqual([c['original_result']['value']['value'] for c in r['cases']],[10,40])

    def test_individual_case_falls_back_to_shared(self):
        src = 'def calculate():\n    return int(input())*2\n'
        cases = [{'function':'calculate','args':[],'kwargs':{}}]
        r = verify_function_results(src,src,cases,stdin='6\n')
        self.assertEqual(r['cases'][0]['original_result']['value']['value'], 12)

    def test_case_input_wrong_type_fails_validation(self):
        src = 'def foo():\n    return 1\n'
        with self.assertRaises(ValueError):
            verify_function_results(src,src,[{'function':'foo','args':[],'kwargs':{},'stdin':5}])

    def test_case_input_overlong_fails_validation(self):
        src = 'def foo():\n    return 1\n'
        with self.assertRaises(ValueError):
            verify_function_results(src,src,[{'function':'foo','args':[],'kwargs':{},'stdin':'x'*8193}])

    def test_shared_input_overlong_fails_validation(self):
        src = 'def foo():\n    return 1\n'
        with self.assertRaises(ValueError):
            verify_function_results(src,src,[{'function':'foo','args':[],'kwargs':{}}], stdin='x'*8193)

    def test_pydantic_request_accepts_stdin(self):
        style = CodingStylePayload(id='x',name='x',description='',syntax_tags=[],concept_tags=[],metrics={},created_at='now')
        req = StyleApplyRequest(language='python', code='print(input())',style=style,stdin='5\n')
        self.assertEqual(req.stdin,'5\n')
        self.assertIsNone(StyleApplyRequest(language='python', code='print(1)',style=style).stdin)

    def test_pydantic_case_stdin_accepted(self):
        from app.schemas.style_apply import FunctionTestCase
        obj=FunctionTestCase(function='foo',args=[],kwargs={},stdin='5\n')
        self.assertEqual(obj.stdin,'5\n')

    def test_legacy_verify_has_no_stdin_argument(self):
        with patch.object(ev, '_verify_observed_execution', return_value={'status':'equivalent'}) as fn:
            ev.verify_execution_equivalence('print(1)','print(1)')
        fn.assert_called_once_with('print(1)','print(1)')

    def test_route_forwards_stdin_to_style_service(self):
        style = CodingStylePayload(id='x',name='x',description='',syntax_tags=[],concept_tags=[],metrics={},created_at='now')
        request = StyleApplyRequest(language='python',code='print(1)',style=style,stdin='5\n')
        service_result=('print(1)','ok',[],[],{'target_analysis':{'syntax_tags':[],'concept_tags':[],'metrics':{}},
                         'missing_syntax_tags':[],'missing_concept_tags':[]},None)
        with patch.object(route,'apply_coding_style',return_value=service_result) as fn:
            response = route.apply_style_api(request)
        self.assertTrue(response.success)
        self.assertEqual(fn.call_args.kwargs['stdin'],'5\n')


if __name__ == '__main__':
    unittest.main()
