"""Formatting concept tags: source evidence, API, persistence and isolation."""
from __future__ import annotations

import json
import unittest

from app.api.routes.analyze import _analyze_formatting_style, _FormattingStyleRequest
from app.schemas.style_apply import CodingStylePayload
from app.services.style_format_concept_tag_service import build_formatting_concept_tags
from app.services.style_format_profile_service import extract_formatting_style
from app.services.style_tag_transform_map_service import get_create_action_for_tag
from app.services.tag_rule_service import CONCEPT_TAG_RULES, get_concept_tag_rule


def tags(code: str) -> dict[str, dict]:
    return {tag["tag"]: tag for tag in build_formatting_concept_tags(extract_formatting_style(code))}


class FormattingConceptTagTests(unittest.TestCase):
    def test_two_concept_tags(self):
        self.assertEqual(set(tags('def f():\n    pass\n')), {'들여쓰기', '줄 바꿈'})

    def test_spaces_four_columns(self):
        info = tags('def f():\n    x = 1\n    return x\n')['들여쓰기']
        self.assertEqual(info['details']['kind'], 'spaces')
        self.assertEqual(info['details']['unit_columns'], 4)

    def test_spaces_two_columns(self):
        info = tags('def f():\n  x = 1\n  return x\n')['들여쓰기']
        self.assertEqual(info['details']['kind'], 'spaces')
        self.assertEqual(info['details']['unit_columns'], 2)

    def test_tabs(self):
        info = tags('def f():\n\tx = 1\n\treturn x\n')['들여쓰기']
        self.assertEqual(info['details']['kind'], 'tabs')

    def test_no_indentation_does_not_invent_unit(self):
        info = tags('x = 1\n')['들여쓰기']
        self.assertEqual(info['score'], 0.0)
        self.assertIsNone(info['details']['unit_columns'])

    def test_lf(self):
        info = tags('x = 1\ny = 2\n')['줄 바꿈']
        self.assertEqual(info['details']['line_endings']['preferred'], 'lf')

    def test_crlf(self):
        info = tags('x = 1\r\ny = 2\r\n')['줄 바꿈']
        self.assertEqual(info['details']['line_endings']['preferred'], 'crlf')

    def test_multiline_parentheses(self):
        info = tags('data = (\n  1,\n  2,\n)\n')['줄 바꿈']
        self.assertGreater(info['details']['line_layout']['multiline_statements'], 0)

    def test_blank_line_details_are_retained(self):
        info = tags('x = 1\n\n\ny = 2\n')['줄 바꿈']
        self.assertIn('blank_lines_between_code_histogram', info['details']['line_layout'])

    def test_empty_code_has_no_fake_evidence(self):
        found = tags('')
        self.assertEqual(found['들여쓰기']['score'], 0.0)
        self.assertEqual(found['줄 바꿈']['score'], 0.0)

    def test_nested_details_are_copied(self):
        profile = extract_formatting_style('def f():\n    pass\n')
        result = build_formatting_concept_tags(profile)
        result[0]['details']['unit_columns'] = 900
        self.assertEqual(profile['indentation']['unit_columns'], 4)

    def test_json_serializable(self):
        self.assertIsInstance(json.loads(json.dumps(list(tags('x=1\n').values()), ensure_ascii=False)), list)

    def test_concept_rules_registered(self):
        self.assertEqual(get_concept_tag_rule('들여쓰기')['category'], '서식')
        self.assertEqual(get_concept_tag_rule('줄 바꿈')['category'], '서식')

    def test_existing_structural_registry_is_not_expanded(self):
        self.assertEqual(len(CONCEPT_TAG_RULES), 41)
        self.assertIsNone(get_create_action_for_tag('들여쓰기'))
        self.assertIsNone(get_create_action_for_tag('줄 바꿈'))

    def test_formatting_endpoint_returns_tags_and_profile(self):
        result = _analyze_formatting_style(_FormattingStyleRequest(code='def f():\n  pass\n'))
        self.assertTrue(result['success'])
        self.assertEqual(len(result['concept_tags']), 2)
        self.assertEqual(result['concept_tags'][0]['details'], result['formatting_style']['indentation'])

    def test_saved_style_schema_retains_tag_details(self):
        saved = CodingStylePayload(
            id='test', name='test', description='', syntax_tags=[],
            concept_tags=list(tags('def f():\n  pass\n').values()),
            metrics={}, created_at='2026-11-16',
            formatting_style=extract_formatting_style('def f():\n  pass\n'),
        )
        payload = saved.model_dump()
        self.assertEqual(payload['concept_tags'][0]['details']['unit_columns'], 2)
        self.assertEqual(payload['concept_tags'][1]['details']['line_endings']['preferred'], 'lf')

    def test_invalid_profile_type_rejected(self):
        with self.assertRaises(TypeError):
            build_formatting_concept_tags(None)


if __name__ == '__main__':
    unittest.main()
