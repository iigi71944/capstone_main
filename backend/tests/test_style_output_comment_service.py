"""Focused tests for final code shown on the Style Apply page."""
from __future__ import annotations

import ast
import io
import tokenize
import unittest

from app.services.style_output_comment_service import strip_style_output_comments as clean


def no_comments_and_docstrings(code: str) -> None:
    tokens = tokenize.generate_tokens(io.StringIO(code).readline)
    assert all(token.type != tokenize.COMMENT for token in tokens)
    tree = ast.parse(code)
    assert not any(isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                   and isinstance(n.value.value, str) for n in ast.walk(tree))


class StyleOutputCommentTests(unittest.TestCase):
    def check(self, before: str, *, content: tuple[str, ...] = ()) -> str:
        after = clean(before)
        ast.parse(after)
        no_comments_and_docstrings(after)
        for literal in content:
            self.assertIn(literal, after)
        self.assertEqual(clean(after), after)
        return after

    def test_basic_hash_line(self):
        self.assertNotIn('# 설명', self.check('# 설명\nx = 1\nprint(x)\n'))

    def test_inline_hash(self):
        out = self.check('value=2  # inline\nprint(value)\n')
        self.assertIn('value=2', out)
        self.assertNotIn('#', out)

    def test_multiple_hashes(self):
        out = self.check('x=1 # first\n# second\ny=2 # third\n')
        self.assertNotIn('#', out)

    def test_hash_in_str_data(self):
        self.check('x="#not a comment"\n', content=('"#not a comment"',))

    def test_hash_in_raw_string_data(self):
        self.check("x=r'#literal' # comment\n", content=("r'#literal'",))

    def test_hash_in_fstring_data(self):
        self.check('x=5\ny=f"#{x}" # note\n', content=('f"#{x}"',))

    def test_basic_triple_single(self):
        out = self.check("'''설명'''\nx=1\n")
        self.assertNotIn('설명', out)

    def test_basic_triple_double(self):
        out = self.check('"""정보"""\nx=1\n')
        self.assertNotIn('정보', out)

    def test_multiline_triple(self):
        out = self.check("'''첫째\n둘째\n셋째'''\nprint('hi')\n")
        self.assertNotIn('첫째', out)
        self.assertNotIn('둘째', out)
        self.assertEqual(out.count('\n'), 4)

    def test_docstring_function_body_with_return(self):
        out = self.check("def f(x):\n    '''docs'''\n    return x+1\n")
        self.assertNotIn('docs', out)
        self.assertIn('return x+1', out)

    def test_docstring_class(self):
        out = self.check("class A:\n    '''docs'''\n    x=3\n")
        self.assertNotIn('docs', out)

    def test_docstring_only_function_becomes_pass(self):
        out = self.check("def f():\n    'x'\n")
        self.assertIn('    pass', out)

    def test_docstring_only_class_becomes_pass(self):
        out = self.check("class C:\n    '''c'''\n")
        self.assertIn('    pass', out)

    def test_docstring_only_if_becomes_pass(self):
        out = self.check("if True:\n    '''x'''\n")
        self.assertIn('    pass', out)

    def test_docstring_only_except_becomes_pass(self):
        out = self.check("try:\n    raise ValueError()\nexcept ValueError:\n    '''doc'''\n")
        self.assertIn('    pass', out)

    def test_multi_string_only_suite_one_pass(self):
        out = self.check("def f():\n    'a'\n    'b'\n")
        self.assertEqual(out.count('pass'), 1)

    def test_unicode_prefix(self):
        out = self.check("한글='값' # 메모\n'''한글 설명'''\nprint(한글)\n")
        self.assertIn('한글=', out)
        self.assertNotIn('메모', out)

    def test_triple_quoted_assignment_preserved(self):
        self.check("text = '''진짜 데이터\n두 번째 줄''' # note\n", content=('진짜 데이터', '두 번째 줄'))

    def test_triple_double_assignment_preserved(self):
        self.check('text = """real data"""\n', content=('"""real data"""',))

    def test_triple_return_preserved(self):
        self.check("def f():\n    return '''value'''\n", content=("'''value'''",))

    def test_triple_argument_preserved(self):
        self.check("print('''message''')\n", content=("'''message'''",))

    def test_triple_inside_collection_preserved(self):
        self.check("items=['''item''']\n", content=("'''item'''",))

    def test_code_with_semicolon_strings(self):
        out = self.check("'''doc'''; x=2\nprint(x)\n")
        self.assertIn('x=2', out)

    def test_inline_string_suite(self):
        out = self.check('if True: "doc"\n')
        self.assertIn('pass', out)

    def test_import_preserved(self):
        self.check('import math  # what\nprint(math.pi)\n', content=('import math',))

    def test_decorator_comments(self):
        self.check('@staticmethod  # note\ndef f(x):\n    return x\n', content=('@staticmethod',))

    def test_async_docstring(self):
        out = self.check('async def f():\n    """notes"""\n    return 1\n')
        self.assertNotIn('notes', out)

    def test_nested_docstring_only(self):
        out = self.check('def f():\n    if True:\n        """doc"""\n')
        self.assertIn('        pass', out)

    def test_crlf_kept(self):
        code = "x=1 # note\r\n'''doc'''\r\nprint(x)\r\n"
        out = self.check(code)
        self.assertNotIn('\n', out.replace('\r\n', ''))

    def test_no_final_newline(self):
        out = self.check('x=1 # no new line')
        self.assertFalse(out.endswith('\n'))

    def test_blank_source(self):
        self.assertEqual(clean(''), '')

    def test_code_without_comments_byte_identical(self):
        code='x=1\r\nprint(x)\r\n'
        self.assertEqual(clean(code), code)

    def test_invalid_syntax_no_crash(self):
        code='def broken(:\n    # note\n'
        self.assertEqual(clean(code), code)

    def test_comment_only_module(self):
        out = self.check('# Only a comment\n')
        self.assertNotIn('#', out)

    def test_lone_docstring_module(self):
        out = self.check('"""module docstring"""\n')
        self.assertNotIn('docstring', out)

    def test_docstring_changing_dunder_doc_is_explicit(self):
        out = self.check('def f():\n    """Original doc"""\n    return 1\n')
        scope = {}
        exec(compile(out, '<trusted_test>', 'exec'), scope)
        self.assertIsNone(scope['f'].__doc__)

    def test_type_ignore_comment_removed(self):
        out = self.check('x = 3  # type: ignore\n')
        self.assertNotIn('type: ignore', out)

    def test_multiline_data_string_with_hash(self):
        self.check("s = '''#data\nline2'''\n", content=('#data',))

    def test_comments_in_complex_nested_structures(self):
        code='''# header
class C:
    """class doc"""
    def f(self, items):
        """function note"""
        result=[]  # init
        for item in items:  # iteration
            if item > 0:
                result.append(item) # keep
        return result
'''
        out=self.check(code)
        self.assertIn('result.append(item)', out)
        self.assertNotIn('class doc', out)


if __name__ == '__main__':
    unittest.main()
