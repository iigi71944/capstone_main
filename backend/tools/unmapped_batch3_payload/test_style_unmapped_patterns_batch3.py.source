"""Built-in, finite regression examples for third unmapped-tag batch.

No submitted/user source is passed to these tests. Each execution case is a
trusted literal snippet fixed in this repository.
"""
from __future__ import annotations

import ast
import contextlib
import io
import unittest

from app.services.improvement.safe_unmapped_patterns_batch3_service import (
    transform_to_augmented_assignment as augmented,
    transform_to_dict_get as dict_get,
)


def observed(source: str):
    result = {}
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(source, '<trusted-fixed-test>', 'exec'), result)
    return out.getvalue(), result.get('result')


class SourceSafetyAssertions(unittest.TestCase):
    def changed_and_equal(self, transform, source: str) -> str:
        output = transform(source)
        self.assertNotEqual(source, output)
        ast.parse(output)
        self.assertEqual(observed(source), observed(output))
        self.assertEqual(transform(output), output)
        return output


class AugmentedAssignmentTests(SourceSafetyAssertions):
    def test_basic_plus(self):
        out = self.changed_and_equal(augmented, 'x=1\nx=x+2\nresult=x\nprint(result)\n')
        self.assertIn('x += 2', out)

    def test_additional_minus(self):
        out = self.changed_and_equal(augmented, 'x=9\nx=x-3\nresult=x\nprint(result)\n')
        self.assertIn('x -= 3', out)

    def test_complex_multiply_inside_function(self):
        out = self.changed_and_equal(augmented, 'def f():\n    n=4\n    n=n*3\n    return n\nresult=f()\nprint(result)\n')
        self.assertIn('n *= 3', out)

    def test_negative_integer_initializer(self):
        self.changed_and_equal(augmented, 'x=-4\nx=x+1\nresult=x\n')

    def test_negative_rhs(self):
        self.changed_and_equal(augmented, 'x=3\nx=x+-2\nresult=x\n')

    def test_zero_rhs(self):
        self.changed_and_equal(augmented, 'x=3\nx=x*0\nresult=x\n')

    def test_unicode(self):
        source = '# 시작\n값=3\n값=값+2\nresult=값\n# 끝\n'
        out = self.changed_and_equal(augmented, source)
        self.assertIn('값 += 2', out)
        self.assertTrue(out.startswith('# 시작\n'))
        self.assertTrue(out.endswith('# 끝\n'))

    def test_crlf_preserved(self):
        out = self.changed_and_equal(augmented, 'x=1\r\nx=x+1\r\nresult=x\r\n')
        self.assertNotIn('\n', out.replace('\r\n', ''))

    def test_two_independent_functions(self):
        code = ('def a():\n    x=1\n    x=x+2\n    return x\n'
                'def b():\n    y=4\n    y=y-3\n    return y\n'
                'result=(a(),b())\n')
        out = self.changed_and_equal(augmented, code)
        self.assertIn('x += 2', out)
        self.assertIn('y -= 3', out)

    def test_nested_if_body(self):
        code = ('if True:\n    x=10\n    x=x*2\nresult=x\n')
        self.changed_and_equal(augmented, code)

    def test_bool_initializer_rejected(self):
        code = 'x=True\nx=x+1\n'; self.assertEqual(augmented(code), code)

    def test_string_initializer_rejected(self):
        code = 'x="a"\nx=x+"b"\n'; self.assertEqual(augmented(code), code)

    def test_list_initializer_rejected(self):
        code = 'x=[]\nx=x+[1]\n'; self.assertEqual(augmented(code), code)

    def test_unproven_initializer_rejected(self):
        code = 'x=read()\nx=x+2\n'; self.assertEqual(augmented(code), code)

    def test_non_adjacent_assignments_rejected(self):
        code = 'x=1\nprint("hey")\nx=x+2\n'; self.assertEqual(augmented(code), code)

    def test_inline_comment_rejected(self):
        code = 'x=1\nx=x+2  # keep\n'; self.assertEqual(augmented(code), code)

    def test_comment_on_initializer_rejected(self):
        code = 'x=1 # keep\nx=x+2\n'; self.assertEqual(augmented(code), code)

    def test_global_rejected(self):
        code = 'x=1\ndef f():\n    global x\n    x=x+2\n'; self.assertEqual(augmented(code), code)

    def test_dynamic_code_rejected(self):
        code = 'x=1\nx=x+2\nprint(locals())\n'; self.assertEqual(augmented(code), code)

    def test_object_math_rejected(self):
        code = 'x=object()\nx=x+2\n'; self.assertEqual(augmented(code), code)

    def test_subtract_reversed_rejected(self):
        code = 'x=1\nx=2-x\n'; self.assertEqual(augmented(code), code)

    def test_division_rejected(self):
        code = 'x=8\nx=x/2\n'; self.assertEqual(augmented(code), code)

    def test_double_augmented_run_idempotent(self):
        code = 'x=1\nx=x+2\nx=x+3\nresult=x\n'
        out = self.changed_and_equal(augmented, code)
        self.assertIn('x += 2', out)
        self.assertIn('x=x+3', out)

    def test_multiline_assignment_rejected(self):
        code = 'x=1\nx=(x+\n   2)\n'; self.assertEqual(augmented(code), code)

    def test_invalid_python_skips(self):
        self.assertEqual(augmented('if:'), 'if:')

    def test_comments_unrelated_preserved(self):
        code = '# top\nx=2\nx=x*3\n# bottom\nresult=x\n'
        out = self.changed_and_equal(augmented, code)
        self.assertIn('# top', out)
        self.assertIn('# bottom', out)


class DictGetTests(SourceSafetyAssertions):
    def test_basic_string_key(self):
        out = self.changed_and_equal(dict_get, 'd={"a":2}\nresult=d["a"]\nprint(result)\n')
        self.assertIn('d.get("a")', out)

    def test_additional_integer_key(self):
        self.changed_and_equal(dict_get, 'd={3:"three"}\nresult=d[3]\nprint(result)\n')

    def test_complex_function_return(self):
        code = 'def f():\n    d={"x":5}\n    return d["x"]\nresult=f()\nprint(result)\n'
        out = self.changed_and_equal(dict_get, code)
        self.assertIn('return d.get("x")', out)

    def test_print_call_form(self):
        self.changed_and_equal(dict_get, 'd={"a":1}\nprint(d["a"])\nresult=d["a"]\n')

    def test_float_key(self):
        self.changed_and_equal(dict_get, 'd={1.5:"float"}\nresult=d[1.5]\n')

    def test_negative_key(self):
        self.changed_and_equal(dict_get, 'd={-2:"n"}\nresult=d[-2]\n')

    def test_bool_key(self):
        self.changed_and_equal(dict_get, 'd={True:"yes"}\nresult=d[True]\n')

    def test_duplicate_key(self):
        self.changed_and_equal(dict_get, 'd={"a":1,"a":2}\nresult=d["a"]\n')

    def test_unicode_text_preserved(self):
        code = '# 시작\n정보={"이름":"민수"}\nresult=정보["이름"]\n# 끝\n'
        out = self.changed_and_equal(dict_get, code)
        self.assertIn('정보.get("이름")', out)
        self.assertTrue(out.startswith('# 시작'))

    def test_crlf_preserved(self):
        code = 'd={"x":2}\r\nresult=d["x"]\r\n'
        out = self.changed_and_equal(dict_get, code)
        self.assertNotIn('\n', out.replace('\r\n', ''))

    def test_many_dicts(self):
        code = ('def a():\n    d={"a":1}\n    return d["a"]\n'
                'def b():\n    d={"b":2}\n    return d["b"]\n'
                'result=(a(),b())\n')
        out = self.changed_and_equal(dict_get, code)
        self.assertEqual(out.count('.get('), 2)

    def test_missing_key_skip(self):
        code = 'd={"a":1}\nresult=d["missing"]\n'; self.assertEqual(dict_get(code), code)

    def test_dynamic_key_skip(self):
        code = 'd={"a":1}\nk="a"\nresult=d[k]\n'; self.assertEqual(dict_get(code), code)

    def test_dynamic_dict_skip(self):
        code = 'd=make_dict()\nresult=d["a"]\n'; self.assertEqual(dict_get(code), code)

    def test_dynamic_dict_value_skip(self):
        code = 'd={"a": f()}\nresult=d["a"]\n'; self.assertEqual(dict_get(code), code)

    def test_nested_value_skip(self):
        code = 'd={"a": [1]}\nresult=d["a"]\n'; self.assertEqual(dict_get(code), code)

    def test_none_dict_value_allowed(self):
        self.changed_and_equal(dict_get, 'd={"a":None}\nresult=d["a"]\n')

    def test_non_adjacent_skip(self):
        code = 'd={"a":1}\nprint("intervening")\nresult=d["a"]\n'; self.assertEqual(dict_get(code), code)

    def test_unsafe_call_skip(self):
        code = 'd={"a":1}\nresult=other(d["a"])\n'; self.assertEqual(dict_get(code), code)

    def test_comment_skip(self):
        code = 'd={"a":1}\nresult=d["a"] # explain\n'; self.assertEqual(dict_get(code), code)

    def test_dynamic_scope_skip(self):
        code = 'd={"a":1}\nresult=d["a"]\nprint(globals())\n'; self.assertEqual(dict_get(code), code)

    def test_class_method(self):
        code = ('class C:\n    def f(self):\n        d={"a":1}\n'
                '        return d["a"]\nresult=C().f()\n')
        self.changed_and_equal(dict_get, code)

    def test_invalid_python_skips(self):
        self.assertEqual(dict_get('if:'), 'if:')

    def test_return_without_value_skip(self):
        code = 'def f():\n    d={"a":1}\n    return\n'; self.assertEqual(dict_get(code), code)


# Integration checks run only in a complete installed project backend.
try:
    from app.services.style_tag_transform_map_service import CREATE_ACTION_BY_TAG, get_tag_transform_status
    from app.services.style_apply_service import _get_transform_function
    from app.services.style_transform_plan_service import build_transform_plan
    from app.services.improvement.counted_while_to_for_service import transform_counted_while_to_for
    from app.services.style_diff_service import compare_style_with_target_code
    _INTEGRATED = True
except ImportError:
    _INTEGRATED = False


@unittest.skipUnless(_INTEGRATED, 'requires complete capstone backend')
class ApplicationIntegrationTests(unittest.TestCase):
    def test_three_tag_links(self):
        expected = {'복합 할당':'create_safe_augmented_assignment',
                    '딕셔너리 메서드 호출':'create_safe_dict_get',
                    'for문':'create_counted_while_to_for'}
        for tag, action in expected.items():
            self.assertEqual(CREATE_ACTION_BY_TAG[tag], action)
            self.assertEqual(get_tag_transform_status(tag), 'linked')
            self.assertTrue(callable(_get_transform_function(action)))

    @staticmethod
    def _plan(style_metrics: dict, target_metrics: dict, concepts=()):
        diff = {'missing_syntax_tags': [], 'missing_concept_tags': [],
                'style_metrics': style_metrics, 'target_analysis': {'metrics':target_metrics},
                'style_concept_names': set(concepts), 'target_concept_names': set(),
                'style_syntax_names': set(), 'target_syntax_names': set()}
        return [a['action'] for a in build_transform_plan(diff)['actions']]

    def test_augmented_metric_preference(self):
        self.assertIn('create_safe_augmented_assignment',
                      self._plan({'aug_assign_count':2}, {'aug_assign_count':0}))

    def test_augmented_preference_requires_style_evidence(self):
        self.assertNotIn('create_safe_augmented_assignment', self._plan({}, {}))

    def test_augmented_target_already_uses_form(self):
        self.assertNotIn('create_safe_augmented_assignment',
                         self._plan({'aug_assign_count':2}, {'aug_assign_count':1}))

    def test_dict_metric_preference(self):
        self.assertIn('create_safe_dict_get',
                      self._plan({'dict_method_call_count':2},{'dict_method_call_count':0},
                                 ('딕셔너리 기반 매핑 구조',)))

    def test_dict_metric_requires_concept(self):
        self.assertNotIn('create_safe_dict_get',
                         self._plan({'dict_method_call_count':2},{'dict_method_call_count':0}))

    def test_dict_metric_target_already_method(self):
        self.assertNotIn('create_safe_dict_get',
                         self._plan({'dict_method_call_count':2},{'dict_method_call_count':1},
                                    ('딕셔너리 기반 매핑 구조',)))

    def test_real_saved_metrics_include_augmented(self):
        target='x=2\nx=x+3\nresult=x\n'
        style={'syntax_tags': [], 'concept_tags': [],
               'metrics': {'aug_assign_count':3}}
        diff=compare_style_with_target_code(style,target)
        self.assertIn('create_safe_augmented_assignment',
                      [a['action'] for a in build_transform_plan(diff)['actions']])

    def test_for_ascending_basic(self):
        code='i=0\nwhile i<4:\n    print(i)\n    i+=1\n'
        changed=transform_counted_while_to_for(code)
        self.assertIn('for i in range(',changed)
        self.assertEqual(observed(code),observed(changed))

    def test_for_descending_additional(self):
        code='i=3\nwhile i>=0:\n    print(i)\n    i-=1\n'
        changed=transform_counted_while_to_for(code)
        self.assertIn('for i in range(',changed)
        self.assertEqual(observed(code),observed(changed))

    def test_for_function_complex(self):
        code=('def f():\n    i=0\n    while i<3:\n        print(i)\n        i+=1\n'
              'f()\n')
        changed=transform_counted_while_to_for(code)
        self.assertIn('for i in range(',changed)
        self.assertEqual(observed(code),observed(changed))


class InstallerSafetyTests(unittest.TestCase):
    """Synthetic repository containing only known anchor structures."""

    @classmethod
    def setUpClass(cls):
        try:
            from tools import install_unmapped_batch3 as installer
        except ImportError:
            cls.installer = None
        else:
            cls.installer = installer

    def setUp(self):
        if self.installer is None:
            self.skipTest('batch3 installation tool unavailable')
        import tempfile
        import shutil
        from pathlib import Path
        from unittest import mock
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root/'.git').mkdir()
        (self.root/'docker-compose.yml').write_text('services: {}\n')
        target_tools = self.root/'backend/tools'
        target_tools.mkdir(parents=True)
        # The installed previous-batch tool scripts are copied byte-for-byte.
        for filename in self.installer.PREVIOUS_TOOLS:
            path = Path(self.installer.__file__).parent/filename
            shutil.copyfile(path, target_tools/filename)
        import runpy
        b1 = runpy.run_path(str(target_tools/'install_unmapped_batch1.py'))
        b2 = runpy.run_path(str(target_tools/'install_unmapped_batch2.py'))
        self.pristine = {
            self.installer.REGISTRY:
                'CREATE_ACTION_BY_TAG: dict[str, str] = {\n}\n',
            self.installer.DISPATCHER:
                'def _get_transform_function(action: str):\n'
                '    action_map = {\n    }\n'
                '    return action_map.get(action)\n',
            self.installer.PLAN:
                'def build_transform_plan(diff):\n'
                '    missing_syntax_tags = []\n'
                '    missing_concept_tags = []\n'
                '    actions = []\n'
                '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n'
                '        tag_name = str(tag_item)\n'
                '        actions.append({\n'
                '            "tag": tag_name,\n'
                '        })\n'
                '    return {"actions": actions}\n',
        }
        for rel, text in self.pristine.items():
            source = text
            if rel == self.installer.REGISTRY:
                source = b2['_patch_registry'](b1['patch_registry'](source))
            elif rel == self.installer.DISPATCHER:
                source = b2['_patch_dispatch'](b1['patch_dispatcher'](source))
            else:
                source = b2['_patch_plan'](source)
            destination = self.root/rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source, encoding='utf-8')
        self.patcher = mock.patch.object(
            self.installer, '_git_original', side_effect=lambda _, rel: self.pristine[rel]
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_five_expected_changes(self):
        self.assertEqual(len(self.installer.plan(self.root)), 5)

    def test_installed_scripts_idempotent(self):
        self.installer.install(self.root)
        self.assertEqual(self.installer.plan(self.root), [])
        self.assertIn('이미', self.installer.install(self.root)[0])

    def test_modified_existing_source_rejected(self):
        path = self.root/self.installer.REGISTRY
        path.write_text(path.read_text()+'\n# unexpected\n')
        with self.assertRaises(self.installer.InstallationError):
            self.installer.plan(self.root)

    def test_missing_prior_tool_rejected(self):
        (self.root/'backend/tools/install_unmapped_batch2.py').unlink()
        with self.assertRaises(self.installer.InstallationError):
            self.installer.plan(self.root)

    def test_backup_contains_previous_files(self):
        old = (self.root/self.installer.REGISTRY).read_bytes()
        self.installer.install(self.root)
        backup = list((self.root/'.git/capstone_install_backups').glob('unmapped_batch3_*'))
        self.assertEqual(len(backup), 1)
        self.assertEqual((backup[0]/self.installer.REGISTRY).read_bytes(), old)

    def test_partial_install_completes(self):
        changes = self.installer.plan(self.root)
        changed = changes[0]
        changed.path.write_bytes(changed.after)
        remaining = self.installer.plan(self.root)
        self.assertEqual(len(remaining), 4)
        self.installer.install(self.root)
        self.assertEqual(len(self.installer.plan(self.root)), 0)


if __name__ == '__main__':
    unittest.main()
