"""형식 취향 추출과 안전 설치가 실제로 동작하는지 검사."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
import json


BACKEND = Path(__file__).resolve().parents[1]


def load_file(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, BACKEND / rel)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


service = load_file("format_service", "app/services/style_format_profile_service.py")
installer = load_file("format_install", "tools/install_formatting_style.py")


class FormattingProfileTests(unittest.TestCase):
    def profile(self, text):
        data = service.extract_formatting_style(text)
        json.dumps(data, ensure_ascii=False)
        self.assertEqual(data["version"], 1)
        return data

    def test_four_spaces(self):
        p = self.profile("def f():\n    x = 1\n    return x\n")
        self.assertEqual(p["indentation"]["kind"], "spaces")
        self.assertEqual(p["indentation"]["unit_columns"], 4)

    def test_two_spaces(self):
        p = self.profile("if True:\n  x=1\n")
        self.assertEqual(p["indentation"]["unit_columns"], 2)

    def test_eight_spaces(self):
        p = self.profile("if True:\n        x=1\n")
        self.assertEqual(p["indentation"]["unit_columns"], 8)

    def test_tabs(self):
        p = self.profile("def f():\n\treturn 3\n")
        self.assertEqual(p["indentation"]["kind"], "tabs")

    def test_nested_indent(self):
        p = self.profile("def f():\n    if True:\n        return 3\n")
        self.assertEqual(p["indentation"]["unit_histogram"], {"4": 2})

    def test_mixed_indents(self):
        p = self.profile("def f():\n \tx = 1\n \treturn x\n")
        self.assertEqual(p["indentation"]["kind"], "mixed")

    def test_flat_code_indentation_unknown(self):
        p = self.profile("x=1\ny=2\n")
        self.assertIsNone(p["indentation"]["kind"])
        self.assertIsNone(p["indentation"]["unit_columns"])

    def test_semicolons(self):
        p = self.profile("a=1; b=2; print(a+b)\n")
        self.assertEqual(p["line_layout"]["semicolon_separators"], 2)
        self.assertTrue(p["line_layout"]["multiple_statements_on_line"])

    def test_newline_statements(self):
        p = self.profile("a=1\nb=2\nprint(a+b)\n")
        self.assertEqual(p["line_layout"]["semicolon_separators"], 0)
        self.assertEqual(p["line_layout"]["logical_statements"], 3)

    def test_semicolon_in_string_ignored(self):
        p = self.profile('text = ";;"\nprint(text)\n')
        self.assertEqual(p["line_layout"]["semicolon_separators"], 0)

    def test_semicolon_in_comment_ignored(self):
        p = self.profile("a = 1 # b=2; c=3\n")
        self.assertEqual(p["line_layout"]["semicolon_separators"], 0)

    def test_parenthesized_multiline(self):
        p = self.profile("result = [\n    1,\n    2,\n]\n")
        self.assertEqual(p["line_layout"]["parenthesized_line_breaks"], 3)
        self.assertEqual(p["line_layout"]["multiline_bracket_groups"], 1)

    def test_one_line_list(self):
        p = self.profile("result = [1, 2]\n")
        self.assertEqual(p["line_layout"]["parenthesized_line_breaks"], 0)

    def test_comment_only_lines_not_code(self):
        p = self.profile("# first\na = 1\n# second\nb = 2\n")
        self.assertEqual(p["line_layout"]["physical_code_lines"], 2)
        self.assertEqual(p["line_layout"]["logical_statements"], 2)

    def test_blank_line_distribution(self):
        p = self.profile("a=1\n\n\nb=2\n")
        self.assertEqual(p["line_layout"]["blank_lines_between_code_histogram"], {"2": 1})

    def test_no_blank_line_distribution(self):
        p = self.profile("a=1\nb=2\n")
        self.assertEqual(p["line_layout"]["blank_lines_between_code_histogram"], {"0": 1})

    def test_crlf(self):
        p = self.profile("a=1\r\nb=2\r\n")
        self.assertEqual(p["line_endings"]["preferred"], "crlf")

    def test_lf(self):
        p = self.profile("a=1\nb=2\n")
        self.assertEqual(p["line_endings"]["preferred"], "lf")

    def test_no_line_ending(self):
        p = self.profile("a=1")
        self.assertIsNone(p["line_endings"]["preferred"])

    def test_empty_source(self):
        p = self.profile("")
        self.assertEqual(p["line_layout"]["logical_statements"], 0)
        self.assertIsNone(p["indentation"]["unit_columns"])

    def test_only_comments(self):
        p = self.profile("# header\n# notes\n")
        self.assertEqual(p["line_layout"]["logical_statements"], 0)

    def test_single_line_docstring_excluded(self):
        p = self.profile('"""explanation"""\nx=1\n')
        self.assertEqual(p["line_layout"]["logical_statements"], 1)

    def test_multiline_docstring_excluded(self):
        p = self.profile('"""first\nsecond\n"""\nx=1\n')
        self.assertEqual(p["line_layout"]["logical_statements"], 1)

    def test_real_string_not_excluded(self):
        p = self.profile("text='''actual data'''\nprint(text)\n")
        self.assertEqual(p["line_layout"]["logical_statements"], 2)

    def test_unicode_source(self):
        p = self.profile('"""설명"""\n한글 = 3\nprint(한글)\n')
        self.assertEqual(p["line_layout"]["logical_statements"], 2)

    def test_mixed_line_endings(self):
        p = self.profile("a=1\r\nb=2\n")
        self.assertEqual(p["line_endings"]["histogram"], {"crlf": 1, "lf": 1})

    def test_validates_python(self):
        with self.assertRaises(SyntaxError):
            self.profile("if True:\nnoindent\n")

    def test_type_guard(self):
        with self.assertRaises(TypeError):
            service.extract_formatting_style(None)

    def test_long_code(self):
        body = "def f():\n" + "".join(f"    a{i} = {i}\n" for i in range(350))
        p = self.profile(body)
        self.assertEqual(p["indentation"]["kind"], "spaces")
        self.assertGreater(p["line_layout"]["physical_code_lines"], 300)

    def test_function_docstring_ignored(self):
        p = self.profile("def f():\n    '''hello'''\n    return 1\n")
        self.assertEqual(p["line_layout"]["logical_statements"], 2)



ROUTE = '''from fastapi import APIRouter
from app.schemas.analysis import AnalyzeRequest, AnalyzeResponse
from app.services.parser_service import parse_code
router = APIRouter()
@router.post("/analyze")
def analyze_code(request: AnalyzeRequest):
    tree = parse_code(request.code)
    return AnalyzeResponse(success=True, syntax_tags=[], concept_tags=[], metrics={}, suggestions=[])
'''
API = '''import type { AnalysisResponse } from "../types/analysis";
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
export async function analyzeCode(code: string): Promise<AnalysisResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/analyze`, {
    method: "POST", body: JSON.stringify({ code }),
  });
  return response.json();
}
'''
HOOK = '''"use client";
import { useMemo, useRef, useState } from "react";
import { analyzeCode } from "../lib/api";
import { buildCodingStyleFromAnalysis, createCodingStyleIdentity } from "../lib/codingStyleFactory";
export function useCodeAnalysis(savedStyleCount: number) {
  const [code, setCodeState] = useState("def example(): pass");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const requestVersion = useRef(0);
  const handleAnalyze = async () => {
    const requestId = ++requestVersion.current;
    try {
      const data = await analyzeCode(code);
      if (requestVersion.current !== requestId) return;
      if (!data.success) { setResult(data); return; }
      setIdentity(createCodingStyleIdentity());
      setResult(data);
    } catch (error) { setLoading(false); }
  };
}
'''
FACTORY = '''import type { AnalysisResponse, CodingStyle } from "../types/analysis";
export function buildCodingStyleFromAnalysis(analysis: AnalysisResponse, options: any) {
  const style: NewCodingStyle = {
    id: options.id,
    syntax_tags: analysis.syntax_tags,
    concept_tags: analysis.concept_tags,
    metrics: analysis.metrics,
    created_at: options.created_at,
    is_shared: false,
  };
  return style;
}
'''
TYPES = '''export type AnalysisResponse = {
  success: boolean;
  syntax_tags: any[];
  concept_tags: any[];
  metrics: Record<string, number>;
};
export type FinalStyleAnalysis = {
  metrics: Record<string, number>;
};
export interface CodingStyle {
  id: string;
  name: string;
  metrics: Record<string, number>;
  created_at: string;
}
'''

class GitAlignedInstallerTests(unittest.TestCase):
    def fixture(self, root, route=ROUTE, api=API, hook=HOOK, factory=FACTORY, types=TYPES):
        for path, content in [
            ('backend/app/api/routes/analyze.py',route),
            ('frontend/lib/api.ts',api),
            ('frontend/hooks/useCodeAnalysis.ts',hook),
            ('frontend/lib/codingStyleFactory.ts',factory),
            ('frontend/types/analysis.ts',types),
        ]:
            file=root/path
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_text(content, encoding='utf-8')
        service_file=root/'backend/app/services/style_format_profile_service.py'
        service_file.parent.mkdir(parents=True,exist_ok=True)
        service_file.write_text('def extract_formatting_style(code): return {}\n',encoding='utf-8')

    def test_route_is_appended(self):
        result, changed=installer._patched_route(ROUTE)
        self.assertTrue(changed)
        self.assertIn('@router.post("/formatting-style")',result)
        compile(result,'<route>','exec')

    def test_route_is_idempotent(self):
        result,_=installer._patched_route(ROUTE)
        self.assertEqual(installer._patched_route(result),(result,False))

    def test_route_preserves_comment_filter(self):
        src=ROUTE.replace('tree = parse_code(request.code)', 'tree = prepare_analysis_tree(parse_code(request.code))')
        result,_=installer._patched_route(src)
        self.assertIn('prepare_analysis_tree(parse_code(request.code))',result)

    def test_route_invalid_python_aborts(self):
        with self.assertRaises(installer.InstallationError):
            installer._patched_route('def broken(: pass')

    def test_route_no_router_aborts(self):
        with self.assertRaises(installer.InstallationError):
            installer._patched_route('x = 1\n')

    def test_route_occupied_aborts(self):
        with self.assertRaises(installer.InstallationError):
            installer._patched_route(ROUTE+'\n@router.post("/formatting-style")\ndef old(): pass')

    def test_api_added(self):
        result,changed=installer._patched_api(API)
        self.assertTrue(changed)
        self.assertIn('`${API_BASE_URL}/api/v1/formatting-style`',result)
        self.assertIn('export async function analyzeFormattingStyle',result)

    def test_api_idempotent(self):
        result,_=installer._patched_api(API)
        self.assertEqual(installer._patched_api(result),(result,False))

    def test_api_missing_known_url_aborts(self):
        with self.assertRaises(installer.InstallationError):
            installer._patched_api('const API_BASE_URL="x";')

    def test_hook_added(self):
        result,_=installer._patched_hook(HOOK)
        self.assertIn('await analyzeFormattingStyle(code)',result)
        self.assertIn('setResult({ ...data, formatting_style: formattingStyle })',result)
        self.assertIn('if (requestVersion.current !== requestId) return;',result)

    def test_hook_preserves_ui(self):
        result,_=installer._patched_hook(HOOK+'\n// JSX_STYLE_BUTTONS_UNMODIFIED')
        self.assertTrue(result.endswith('// JSX_STYLE_BUTTONS_UNMODIFIED'))

    def test_hook_idempotent(self):
        result,_=installer._patched_hook(HOOK)
        self.assertEqual(installer._patched_hook(result),(result,False))

    def test_hook_wrong_structure_aborts(self):
        with self.assertRaises(installer.InstallationError):
            installer._patched_hook(HOOK.replace('setResult(data);','setNewResult(data);'))

    def test_factory_added(self):
        result,_=installer._patched_factory(FACTORY)
        self.assertIn('formatting_style: analysis.formatting_style',result)
        self.assertIn('metrics: analysis.metrics',result)

    def test_factory_idempotent(self):
        result,_=installer._patched_factory(FACTORY)
        self.assertEqual(installer._patched_factory(result),(result,False))

    def test_factory_missing_metrics_aborts(self):
        with self.assertRaises(installer.InstallationError):
            installer._patched_factory(FACTORY.replace('metrics: analysis.metrics,','metrics: {},'))

    def test_types_added_only_to_analysis_and_style(self):
        result,_=installer._patched_types(TYPES)
        self.assertEqual(result.count('formatting_style?: Record<string, unknown>'),2)
        self.assertIn('FinalStyleAnalysis = {\n  metrics: Record<string, number>;',result)

    def test_types_idempotent(self):
        result,_=installer._patched_types(TYPES)
        self.assertEqual(installer._patched_types(result),(result,False))

    def test_missing_type_aborts(self):
        with self.assertRaises(installer.InstallationError):
            installer._patched_types('export type AnalysisResponse = { metrics: Record<string, number>; };')

    def test_plan_project(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            self.fixture(root)
            plan=installer.plan(root)
            self.assertEqual(len(plan),5)
            self.assertFalse(any('/page.tsx' in str(x.path) for x in plan))
            self.assertFalse(any('/useCodingStyles.ts' in str(x.path) for x in plan))

    def test_install_success_and_idempotence(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); self.fixture(root)
            output=installer.install(root,root/'backups')
            self.assertEqual(len(output),6)
            self.assertIn('이미 연결되어',installer.install(root,root/'backups')[0])

    def test_install_preflight_does_not_change_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); self.fixture(root,hook=HOOK.replace('setResult(data);','someOtherFunction();'))
            paths=[root/name for name in ('backend/app/api/routes/analyze.py','frontend/lib/api.ts','frontend/hooks/useCodeAnalysis.ts','frontend/lib/codingStyleFactory.ts','frontend/types/analysis.ts')]
            olds=[p.read_bytes() for p in paths]
            with self.assertRaises(installer.InstallationError): installer.install(root)
            self.assertEqual([p.read_bytes() for p in paths],olds)

    def test_crlf_and_bom_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); self.fixture(root)
            path=root/'frontend/hooks/useCodeAnalysis.ts'
            path.write_bytes(b'\xef\xbb\xbf'+HOOK.replace('\n','\r\n').encode('utf-8'))
            installer.install(root,root/'backups')
            contents=path.read_bytes()
            self.assertTrue(contents.startswith(b'\xef\xbb\xbf'))
            self.assertIn(b'\r\n',contents)
            self.assertEqual(contents.count(b'\n'),contents.count(b'\r\n'))

    def test_backup_original_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); self.fixture(root)
            installer.install(root,root/'backups')
            self.assertEqual((root/'backups/frontend/hooks/useCodeAnalysis.ts').read_text(),HOOK)

    def test_missing_service_aborts(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); self.fixture(root)
            (root/'backend/app/services/style_format_profile_service.py').unlink()
            with self.assertRaises(installer.InstallationError): installer.plan(root)

    def test_untouched_ui_has_no_mark(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); self.fixture(root)
            (root/'frontend/app/page.tsx').parent.mkdir(parents=True,exist_ok=True)
            (root/'frontend/app/page.tsx').write_text('ORIGINAL UI\n')
            installer.install(root,root/'backups')
            self.assertEqual((root/'frontend/app/page.tsx').read_text(),'ORIGINAL UI\n')

if __name__ == '__main__':
    unittest.main()
