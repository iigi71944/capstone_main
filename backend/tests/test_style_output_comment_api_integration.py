"""Route-level integration checks for the final Style Apply response.

They rely on the existing FastAPI/Pydantic project, and do NOT execute submitted
source: both style transform and verification are mocked.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.api.routes import style_apply as route
from app.schemas.style_apply import CodingStylePayload, StyleApplyRequest


def request(code: str) -> StyleApplyRequest:
    return StyleApplyRequest(
        language='python', code=code,
        style=CodingStylePayload(
            id='comment-test', name='Keep existing format', description='',
            syntax_tags=[], concept_tags=[], metrics={}, created_at='2026-11-15',
            formatting_style=None,
        ),
    )


def verification(status: str = 'equivalent') -> dict:
    equivalent = {'equivalent': True, 'different': False, 'not_verified': None}[status]
    result = {
        'success': True, 'stdout': '1\n', 'stderr': '', 'exit_code': 0,
        'timed_out': False, 'blocked': False, 'block_reason': None,
    }
    return {
        'source': 'runtime', 'status': status, 'equivalent': equivalent,
        'original': dict(result), 'transformed': dict(result),
        'message': 'verification',
    }


def original_tuple(code: str, execution_verification=None):
    return (
        code, '기존 분석 요약', [], [],
        {'target_analysis': {'syntax_tags': [], 'concept_tags': [], 'metrics': {}},
         'missing_syntax_tags': [], 'missing_concept_tags': []},
        execution_verification,
    )


class StyleOutputRouteIntegration(unittest.TestCase):
    def test_hash_comments_are_absent_in_displayed_transformed_code(self):
        source = '# head\nx=1  # inline\nprint(x)\n'
        with patch.object(route, 'apply_coding_style', return_value=original_tuple(source)):
            with patch.object(route, 'verify_execution_equivalence', return_value=verification()) as verifier:
                response = route.apply_style_api(request(source))
        self.assertTrue(response.success)
        self.assertNotIn('# head', response.transformed_code)
        self.assertNotIn('# inline', response.transformed_code)
        self.assertEqual(response.original_code, source)
        self.assertEqual(response.execution_verification.status, 'equivalent')
        verifier.assert_called_once()

    def test_docstrings_removed_but_actual_data_preserved(self):
        source = "'''header'''\ndef f():\n    '''docs'''\n    return '''actual data'''\n"
        with patch.object(route, 'apply_coding_style', return_value=original_tuple(source)):
            with patch.object(route, 'verify_execution_equivalence', return_value=verification()):
                response = route.apply_style_api(request(source))
        self.assertTrue(response.success)
        self.assertNotIn('header', response.transformed_code)
        self.assertNotIn('docs', response.transformed_code)
        self.assertIn("'''actual data'''", response.transformed_code)

    def test_clean_source_does_not_reverify(self):
        source = 'x=1\nprint(x)\n'
        with patch.object(route, 'apply_coding_style', return_value=original_tuple(source)):
            with patch.object(route, 'verify_execution_equivalence') as verifier:
                response = route.apply_style_api(request(source))
        self.assertEqual(response.transformed_code, source)
        verifier.assert_not_called()

    def test_different_verification_keeps_requested_comment_removal(self):
        source = 'def f():\n    """value"""\n    return 1\nprint(f.__doc__)\n'
        with patch.object(route, 'apply_coding_style', return_value=original_tuple(source)):
            with patch.object(route, 'verify_execution_equivalence', return_value=verification('different')):
                response = route.apply_style_api(request(source))
        self.assertNotIn('"""value"""', response.transformed_code)
        self.assertEqual(response.execution_verification.status, 'different')
        self.assertTrue(any('__doc__' in warning for warning in response.warnings))

    def test_not_verified_is_disclosed(self):
        source = '# note\nprint(1)\n'
        with patch.object(route, 'apply_coding_style', return_value=original_tuple(source)):
            with patch.object(route, 'verify_execution_equivalence', return_value=verification('not_verified')):
                response = route.apply_style_api(request(source))
        self.assertNotIn('# note', response.transformed_code)
        self.assertEqual(response.execution_verification.status, 'not_verified')
        self.assertTrue(response.warnings)

    def test_invalid_verification_is_not_reported_as_equivalent(self):
        source = 'print(1) # note\n'
        with patch.object(route, 'apply_coding_style', return_value=original_tuple(source, verification())):
            with patch.object(route, 'verify_execution_equivalence', return_value={'status': 'equivalent'}):
                response = route.apply_style_api(request(source))
        self.assertNotIn('# note', response.transformed_code)
        self.assertIsNone(response.execution_verification)
        self.assertTrue(response.warnings)

    def test_verifier_exception_does_not_restore_comments(self):
        source = '# note\nprint(1)\n'
        with patch.object(route, 'apply_coding_style', return_value=original_tuple(source)):
            with patch.object(route, 'verify_execution_equivalence', side_effect=RuntimeError):
                response = route.apply_style_api(request(source))
        self.assertNotIn('# note', response.transformed_code)
        self.assertIsNone(response.execution_verification)
        self.assertTrue(response.warnings)

    def test_comment_after_transformed_code_also_removed(self):
        source = 'a=1\n'; transformed = 'a=1 # generated note\n'
        with patch.object(route, 'apply_coding_style', return_value=original_tuple(transformed)):
            with patch.object(route, 'verify_execution_equivalence', return_value=verification()):
                response = route.apply_style_api(request(source))
        self.assertIn('a=1', response.transformed_code)
        self.assertNotIn('generated note', response.transformed_code)

    def test_non_python_language_still_fails(self):
        original = request('print(1) # note')
        request_data = original.model_dump()
        request_data['language'] = 'javascript'
        response = route.apply_style_api(StyleApplyRequest.model_validate(request_data))
        self.assertFalse(response.success)
        self.assertEqual(response.transformed_code, '')

    def test_empty_result_validates_without_comments(self):
        source = '"""only doc"""\n'
        with patch.object(route, 'apply_coding_style', return_value=original_tuple(source)):
            with patch.object(route, 'verify_execution_equivalence', return_value=verification()):
                response = route.apply_style_api(request(source))
        self.assertNotIn('only doc', response.transformed_code)


if __name__ == '__main__':
    unittest.main()
