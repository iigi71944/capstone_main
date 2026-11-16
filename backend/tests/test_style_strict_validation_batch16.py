"""Batch 16 opt-in strict validation; verifies API, behavior, cleanup and legacy flow.

Mocks runtime verification and transformations. Never executes submitted code.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.api.routes import style_apply as route
from app.schemas.style_apply import CodingStylePayload, StyleApplyRequest
from app.services import style_apply_service as service


def make_request(code='print(1)\n', *, strict=False, profile=None):
    return StyleApplyRequest(
        language='python', code=code,
        style=CodingStylePayload(
            id='batch16', name='Strict', description='',
            syntax_tags=[], concept_tags=[], metrics={},
            created_at='2026-11-16', formatting_style=profile,
        ),
        strict_runtime_validation=strict,
    )


def verdict(status='equivalent'):
    equivalent = {'equivalent': True, 'different': False, 'not_verified': None}[status]
    result = {'success': True, 'stdout': '1\n', 'stderr': '', 'exit_code': 0,
              'blocked': False, 'timed_out': False, 'block_reason': None}
    return {'source': 'runtime', 'status': status, 'equivalent': equivalent,
            'original': dict(result), 'transformed': dict(result),
            'message': 'batch16 fixture'}


def style_result(code, verification=None):
    return (code, '기존 분석 요약', [], [],
            {'target_analysis': {'syntax_tags': [], 'concept_tags': [], 'metrics': {}},
             'missing_syntax_tags': [], 'missing_concept_tags': []}, verification)


class StrictSchemaTests(unittest.TestCase):
    def test_default_is_false(self):
        self.assertIs(make_request().strict_runtime_validation, False)

    def test_true_roundtrip(self):
        request = make_request(strict=True)
        self.assertIs(request.strict_runtime_validation, True)
        self.assertIs(StyleApplyRequest.model_validate(request.model_dump()).strict_runtime_validation, True)

    def test_boolean_only(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            StyleApplyRequest.model_validate({**make_request().model_dump(),
                                               'strict_runtime_validation': 'not-a-bool'})

    def test_existing_style_has_no_new_required_fields(self):
        self.assertIs(make_request().style.formatting_style, None)


class StrictRouteTests(unittest.TestCase):
    def test_false_flag_forwarded(self):
        with patch.object(route, 'apply_coding_style', return_value=style_result('print(1)\n')) as fn:
            route.apply_style_api(make_request(strict=False))
        self.assertIs(fn.call_args.kwargs['strict_runtime_validation'], False)

    def test_true_flag_forwarded(self):
        with patch.object(route, 'apply_coding_style', return_value=style_result('print(1)\n')) as fn:
            route.apply_style_api(make_request(strict=True))
        self.assertIs(fn.call_args.kwargs['strict_runtime_validation'], True)

    def _cleanup(self, status, *, strict, prior=None, source='# note\nprint(1)\n'):
        with patch.object(route, 'apply_coding_style', return_value=style_result(source, prior)), \
             patch.object(route, 'verify_execution_equivalence', return_value=(
                 verdict(status) if status != 'malformed' else {'status':'equivalent'})):
            return route.apply_style_api(make_request(source, strict=strict))

    def test_strict_cleanup_equivalent_remains(self):
        r = self._cleanup('equivalent', strict=True)
        self.assertNotIn('# note', r.transformed_code)
        self.assertEqual(r.execution_verification.status, 'equivalent')

    def test_strict_cleanup_different_rolled_back(self):
        r = self._cleanup('different', strict=True)
        self.assertEqual(r.transformed_code, '# note\nprint(1)\n')
        self.assertTrue(any('엄격 실행 검증' in x for x in r.warnings))
        self.assertIn('제거를 취소', r.summary)

    def test_strict_cleanup_not_verified_rolled_back(self):
        r = self._cleanup('not_verified', strict=True)
        self.assertEqual(r.transformed_code, '# note\nprint(1)\n')

    def test_strict_cleanup_malformed_rolled_back(self):
        r = self._cleanup('malformed', strict=True)
        self.assertEqual(r.transformed_code, '# note\nprint(1)\n')

    def test_strict_cleanup_preserves_prior_verdict(self):
        prior = verdict('equivalent')
        r = self._cleanup('different', strict=True, prior=prior)
        self.assertEqual(r.transformed_code, '# note\nprint(1)\n')
        self.assertEqual(r.execution_verification.status, 'equivalent')

    def test_default_cleanup_different_still_removes(self):
        r = self._cleanup('different', strict=False)
        self.assertNotIn('# note', r.transformed_code)
        self.assertEqual(r.execution_verification.status, 'different')

    def test_default_cleanup_not_verified_still_removes(self):
        r = self._cleanup('not_verified', strict=False)
        self.assertNotIn('# note', r.transformed_code)
        self.assertEqual(r.execution_verification.status, 'not_verified')

    def test_strict_cleanup_verifier_exception_rolled_back(self):
        source='# note\nprint(1)\n'
        with patch.object(route, 'apply_coding_style', return_value=style_result(source)), \
             patch.object(route, 'verify_execution_equivalence', side_effect=ValueError('no')):
            r=route.apply_style_api(make_request(source, strict=True))
        self.assertEqual(r.transformed_code, source)

    def test_strict_format_not_verified_rolled_back(self):
        from app.services.style_format_profile_service import extract_formatting_style
        source='def f():\n    print(1)\n'
        profile=extract_formatting_style('def f():\n  print(1)\n')
        with patch.object(route, 'apply_coding_style', return_value=style_result(source)), \
             patch.object(route, 'verify_execution_equivalence', return_value=verdict('not_verified')):
            r=route.apply_style_api(make_request(source, strict=True, profile=profile))
        self.assertEqual(r.transformed_code, source)
        self.assertTrue(any('서식 변경을 취소' in x for x in r.warnings))

    def test_default_format_not_verified_preserved(self):
        from app.services.style_format_profile_service import extract_formatting_style
        source='def f():\n    print(1)\n'
        profile=extract_formatting_style('def f():\n  print(1)\n')
        with patch.object(route, 'apply_coding_style', return_value=style_result(source)), \
             patch.object(route, 'verify_execution_equivalence', return_value=verdict('not_verified')):
            r=route.apply_style_api(make_request(source, strict=False, profile=profile))
        self.assertNotEqual(r.transformed_code, source)


class StrictServiceTests(unittest.TestCase):
    ORIGINAL = 'print(1)\n'
    MODIFIED = 'print(2)\n'

    def _service(self, *, strict, result):
        from unittest.mock import patch
        with patch.object(service, 'compare_style_with_target_code', return_value={}), \
             patch.object(service, 'build_transform_plan', return_value={
                 'actions': [{'action':'test','tag':'테스트','reason':'batch16'}],
                 'compare_only': []}), \
             patch.object(service, '_get_transform_function', return_value=lambda code: self.MODIFIED), \
             patch.object(service, 'compare_after_transform', return_value={
                 'missing_syntax_tags': [], 'missing_concept_tags': []}), \
             patch.object(service, 'verify_execution_equivalence', return_value=verdict(result)):
            return service.apply_coding_style(self.ORIGINAL, {}, strict_runtime_validation=strict)

    def test_strict_service_unknown_reverts(self):
        r=self._service(strict=True,result='not_verified')
        self.assertEqual(r[0],self.ORIGINAL)
        self.assertEqual(r[2],[])

    def test_default_service_unknown_keeps(self):
        r=self._service(strict=False,result='not_verified')
        self.assertEqual(r[0],self.MODIFIED)

    def test_strict_service_equivalent_keeps(self):
        r=self._service(strict=True,result='equivalent')
        self.assertEqual(r[0],self.MODIFIED)

    def test_strict_service_different_reverts(self):
        r=self._service(strict=True,result='different')
        self.assertEqual(r[0],self.ORIGINAL)


if __name__ == '__main__':
    unittest.main()
