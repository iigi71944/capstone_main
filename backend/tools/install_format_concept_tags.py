"""Install formatting concept tags on capstone_main (base: e9f4b6b).

Compatible with Batch 15, since none of its edited paths overlap this patch.
Preflight all targets, preserve BOM/CRLF, keep backups in .git, rollback on
write errors, reject partial installs and unexpected source modifications.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1
import os
from pathlib import Path
import sys
import tempfile

BASE_BLOBS = {
    'backend/app/api/routes/analyze.py': '5004d4347f63fe17bb04639ebe06f159d7d59269',
    'backend/app/services/tag_rule_service.py': 'f9d03537dc6c94aecebe474ea714cadb5b84d96b',
    'backend/app/schemas/style_apply.py': '5d5a8ec9a436667246286dbcb5f3e58abee340d7',
    'frontend/lib/api.ts': '146f746f2bc796e4008e3ef2e182e2a87be5493f',
    'frontend/hooks/useCodeAnalysis.ts': '6e166e7b8d25d80c23cbd18fe096e7754eb08e05',
    'frontend/types/analysis.ts': 'bf76316b7fd437006420b009a5947de721506b5b',
    'frontend/app/tags.tsx': 'b8a3932c3601a60bbada32383ce67a63883da55b',
    'frontend/components/sections/StyleSection.tsx': 'fd90886ef588d884501820113b81334b3b0d89c5',
}
MARKERS = {
    'backend/app/api/routes/analyze.py': 'CAPSTONE_FORMAT_CONCEPT_API_V1',
    'backend/app/services/tag_rule_service.py': 'CAPSTONE_FORMAT_CONCEPT_RULES_V1',
    'backend/app/schemas/style_apply.py': 'CAPSTONE_FORMAT_CONCEPT_SCHEMA_V1',
    'frontend/lib/api.ts': 'CAPSTONE_FORMAT_CONCEPT_FETCH_V1',
    'frontend/hooks/useCodeAnalysis.ts': 'CAPSTONE_FORMAT_CONCEPT_MERGE_V1',
    'frontend/types/analysis.ts': 'CAPSTONE_FORMAT_CONCEPT_TYPES_V1',
    'frontend/app/tags.tsx': 'CAPSTONE_FORMAT_CONCEPT_DOCS_V1',
    'frontend/components/sections/StyleSection.tsx': 'CAPSTONE_FORMAT_CONCEPT_LIST_V1',
}
PAYLOAD = {
    'backend/app/services/style_format_concept_tag_service.py': 'style_format_concept_tag_service.py.source',
    'backend/tests/test_format_concept_tags.py': 'test_format_concept_tags.py.source',
}
PAYLOAD_DIR = Path(__file__).resolve().parent / 'format_tag_payload'


class PatchError(Exception):
    pass


@dataclass(frozen=True)
class Change:
    path: Path
    before: bytes | None
    after: bytes


def _decode(data: bytes) -> tuple[str, bool, bool]:
    bom = data.startswith(b'\xef\xbb\xbf')
    raw = data[3:] if bom else data
    return raw.decode('utf-8').replace('\r\n', '\n'), bom, b'\r\n' in raw


def _encode(source: str, bom: bool, crlf: bool) -> bytes:
    if crlf:
        source = source.replace('\n', '\r\n')
    return (b'\xef\xbb\xbf' if bom else b'') + source.encode('utf-8')


def _blob(source: str) -> str:
    data = source.encode('utf-8')
    return sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def _once(source: str, old: str, new: str, path: str) -> str:
    if source.count(old) != 1:
        raise PatchError(f'{path}: 예상한 삽입 위치를 1개 찾지 못했습니다.')
    return source.replace(old, new, 1)


def _patch(path: str, source: str) -> str:
    if path == 'backend/app/api/routes/analyze.py':
        source = _once(source,
            'from app.services.concept_tag_service import extract_concept_tags\n',
            'from app.services.concept_tag_service import extract_concept_tags\n'
            '# CAPSTONE_FORMAT_CONCEPT_API_V1\n'
            'from app.services.style_format_concept_tag_service import build_formatting_concept_tags\n', path)
        return _once(source,
            '    return {"success": True, "formatting_style": profile}\n',
            '    return {"success": True, "formatting_style": profile,\n'
            '            "concept_tags": build_formatting_concept_tags(profile)}\n', path)

    if path == 'backend/app/services/tag_rule_service.py':
        source = _once(source, 'def get_syntax_tag_rule(tag_name: str) -> dict:\n',
            '# CAPSTONE_FORMAT_CONCEPT_RULES_V1\n'
            '# Formatting-only concept tags intentionally live outside the historical\n'
            '# 41 structural concept rules (and 102-tag transform registry).\n'
            'FORMATTING_CONCEPT_TAG_RULES = {\n'
            '    "들여쓰기": {"category": "서식", "concept_level": "표현 구조",\n'
            '               "difficulty": "기본 구조", "style_role": "들여쓰기 선호 저장"},\n'
            '    "줄 바꿈": {"category": "서식", "concept_level": "표현 구조",\n'
            '               "difficulty": "기본 구조", "style_role": "줄 배치 선호 저장"},\n'
            '}\n\n\n'
            'def get_syntax_tag_rule(tag_name: str) -> dict:\n', path)
        # Patch only the concept-rule function, not unrelated fallback dicts.
        begin = source.index('def get_concept_tag_rule(tag_name: str) -> dict:')
        finish = source.index('def enrich_syntax_tag(', begin)
        block = source[begin:finish]
        block = _once(block,
            '    return CONCEPT_TAG_RULES.get(tag_name, {',
            '    return CONCEPT_TAG_RULES.get(tag_name, FORMATTING_CONCEPT_TAG_RULES.get(tag_name, {', path)
        if block.count('    })') != 1:
            raise PatchError(path + ': concept fallback closing not found')
        block = block.replace('    })', '    }))', 1)
        return source[:begin] + block + source[finish:]

    if path == 'backend/app/schemas/style_apply.py':
        return _once(source,
            'class StyleTagItem(BaseModel):\n    tag: str\n    count: Optional[int] = None\n    score: Optional[float] = None\n    reason: Optional[str] = None\n',
            'class StyleTagItem(BaseModel):\n    tag: str\n    count: Optional[int] = None\n'
            '    score: Optional[float] = None\n    reason: Optional[str] = None\n'
            '    details: Optional[Dict[str, Any]] = None  # CAPSTONE_FORMAT_CONCEPT_SCHEMA_V1\n', path)

    if path == 'frontend/lib/api.ts':
        source = _once(source, '  CodingStyle,\n  FunctionTestCase,',
                       '  CodingStyle,\n  ConceptTag,\n  FunctionTestCase,', path)
        source = _once(source,
            'export async function analyzeFormattingStyle(\n  code: string\n): Promise<Record<string, unknown>> {',
            '// CAPSTONE_FORMAT_CONCEPT_FETCH_V1\n'
            'export async function analyzeFormattingStyle(\n  code: string\n): Promise<{ formatting_style: Record<string, unknown>; concept_tags: ConceptTag[] }> {', path)
        source = _once(source,
            '  const result = data as { success?: boolean; formatting_style?: unknown };',
            '  const result = data as { success?: boolean; formatting_style?: unknown; concept_tags?: unknown };', path)
        return _once(source,
            '  return result.formatting_style as Record<string, unknown>;',
            '  const conceptTags: ConceptTag[] = Array.isArray(result.concept_tags)\n'
            '    ? result.concept_tags.filter((item: unknown): item is ConceptTag => (\n'
            '        typeof item === "object" && item !== null &&\n'
            '        typeof (item as Record<string, unknown>).tag === "string"\n'
            '      ))\n'
            '    : [];\n'
            '  return {\n'
            '    formatting_style: result.formatting_style as Record<string, unknown>,\n'
            '    concept_tags: conceptTags,\n'
            '  };', path)

    if path == 'frontend/hooks/useCodeAnalysis.ts':
        return _once(source,
            '      const formattingStyle = await analyzeFormattingStyle(code);\n'
            '      if (requestVersion.current !== requestId) return;\n'
            '      setIdentity(createCodingStyleIdentity());\n'
            '      setResult({ ...data, formatting_style: formattingStyle });',
            '      // CAPSTONE_FORMAT_CONCEPT_MERGE_V1\n'
            '      const formattingAnalysis = await analyzeFormattingStyle(code);\n'
            '      if (requestVersion.current !== requestId) return;\n'
            '      const formattingNames = new Set(["들여쓰기", "줄 바꿈"]);\n'
            '      setIdentity(createCodingStyleIdentity());\n'
            '      setResult({\n'
            '        ...data,\n'
            '        concept_tags: [\n'
            '          ...data.concept_tags.filter((tag) => !formattingNames.has(tag.tag)),\n'
            '          ...formattingAnalysis.concept_tags.filter((tag) => formattingNames.has(tag.tag)),\n'
            '        ],\n'
            '        formatting_style: formattingAnalysis.formatting_style,\n'
            '      });', path)

    if path == 'frontend/types/analysis.ts':
        return _once(source,
            'export type ConceptTag = {\n  tag: string;\n',
            'export type ConceptTag = {\n  tag: string;\n'
            '  details?: Record<string, unknown> | null; // CAPSTONE_FORMAT_CONCEPT_TYPES_V1\n', path)

    if path == 'frontend/app/tags.tsx':
        return _once(source,
            'export const conceptTagDocs = [\n',
            'export const conceptTagDocs = [\n'
            '  // CAPSTONE_FORMAT_CONCEPT_DOCS_V1\n'
            '  { tag: "들여쓰기", desc: "원본 Python 코드에서 관측한 공백·탭 종류, 들여쓰기 간격과 사용 분포를 저장합니다." },\n'
            '  { tag: "줄 바꿈", desc: "문장별 줄 배치, 빈 줄 분포, 괄호 안 줄 바꿈 및 LF/CRLF 정보를 저장합니다." },\n', path)

    if path == 'frontend/components/sections/StyleSection.tsx':
        return _once(source,
            '                      {style.concept_tags.map((tag, idx) => (\n'
            '                        <span\n'
            '                          key={idx}\n'
            '                          className="px-2.5 py-1 rounded-full bg-purple-100 text-purple-800 text-xs font-medium"\n'
            '                        >\n'
            '                          {tag.tag}\n'
            '                        </span>\n'
            '                      ))}',
            '                      {/* CAPSTONE_FORMAT_CONCEPT_LIST_V1 */}\n'
            '                      {style.concept_tags.map((tag, idx) => (\n'
            '                        tag.details ? (\n'
            '                          <details key={idx} className="w-full rounded-lg border border-purple-200 bg-white p-2 text-xs">\n'
            '                            <summary className="cursor-pointer font-semibold text-purple-800">{tag.tag} · 상세 정보</summary>\n'
            '                            {tag.reason && <p className="mt-2 text-slate-700">{tag.reason}</p>}\n'
            '                            <pre className="mt-2 whitespace-pre-wrap break-words font-mono text-[11px] text-slate-600">\n'
            '                              {JSON.stringify(tag.details, null, 2)}\n'
            '                            </pre>\n'
            '                          </details>\n'
            '                        ) : (\n'
            '                          <span\n'
            '                            key={idx}\n'
            '                            className="px-2.5 py-1 rounded-full bg-purple-100 text-purple-800 text-xs font-medium"\n'
            '                          >\n'
            '                            {tag.tag}\n'
            '                          </span>\n'
            '                        )\n'
            '                      ))}', path)
    raise PatchError('Unknown target: ' + path)


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('wb', dir=path.parent, prefix='.format_tags_', suffix='.tmp', delete=False) as fp:
        tmp = Path(fp.name)
        fp.write(data)
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def preflight(root: Path) -> list[Change]:
    root = root.resolve()
    if not (root / '.git').is_dir() or not (root / 'backend/app/services').is_dir():
        raise PatchError('capstone_main 최상위 폴더(.git 포함)에서 실행해 주세요.')
    markers_found: list[bool] = []
    changes: list[Change] = []
    for relative, expected_sha in BASE_BLOBS.items():
        path = root / relative
        if not path.is_file():
            raise PatchError('대상 파일 누락: ' + relative)
        previous = path.read_bytes()
        src, bom, crlf = _decode(previous)
        installed = MARKERS[relative] in src
        markers_found.append(installed)
        if installed:
            if src.count(MARKERS[relative]) != 1:
                raise PatchError('마커 중복/비정상: ' + relative)
            continue
        if _blob(src) != expected_sha:
            raise PatchError('GitHub e9f4b6b 기준과 파일 내용이 다릅니다. 덮어쓰지 않음: ' + relative)
        updated = _patch(relative, src)
        if relative.endswith('.py'):
            ast.parse(updated, filename=relative)
        changes.append(Change(path, previous, _encode(updated, bom, crlf)))
    if any(markers_found) and not all(markers_found):
        raise PatchError('일부 파일에만 패치가 적용되었습니다. 자동 덮어쓰기를 중단합니다.')
    for relative, payload_name in PAYLOAD.items():
        source_path = PAYLOAD_DIR / payload_name
        target = root / relative
        if not source_path.is_file():
            raise PatchError('패키지 파일 누락: ' + payload_name)
        content = source_path.read_bytes()
        ast.parse(content.decode('utf-8'), filename=payload_name)
        if target.exists():
            if not target.is_file() or _decode(target.read_bytes())[0] != _decode(content)[0]:
                raise PatchError('기존 파일과 이름이 충돌합니다: ' + relative)
        else:
            if any(markers_found):
                raise PatchError('일부 신규 파일이 누락된 상태입니다: ' + relative)
            changes.append(Change(target, None, content))
    if all(markers_found) and changes:
        raise PatchError('설치 완료 표시가 있지만 신규 파일이 누락되어 있습니다.')
    return changes


def install(root: Path) -> None:
    root = root.resolve()
    changes = preflight(root)
    if not changes:
        print('이미 설치되어 있습니다. 변경할 파일이 없습니다.')
        return
    backup_root = root / '.git' / 'format_concept_tag_backups' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup_root.mkdir(parents=True, exist_ok=False)
    for change in changes:
        if change.before is not None:
            backup = backup_root / change.path.relative_to(root)
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(change.before)
    committed: list[Change] = []
    try:
        for change in changes:
            if (change.before is None and change.path.exists()) or (change.before is not None and change.path.read_bytes() != change.before):
                raise PatchError('사전 검사 후 파일이 바뀌었습니다: ' + str(change.path))
            _write_atomic(change.path, change.after)
            committed.append(change)
        if preflight(root):
            raise PatchError('설치 후 검증에서 미적용 파일이 발견됐습니다.')
    except Exception as error:
        for change in reversed(committed):
            if change.before is None:
                change.path.unlink(missing_ok=True)
            else:
                _write_atomic(change.path, change.before)
        raise PatchError('설치 실패로 기존 파일을 복원했습니다: ' + str(error)) from error
    print(f'서식 개념 태그 설치 완료: {len(changes)}개 파일 변경/추가. 백업: {backup_root}')
    print('기존 102개 변환 태그, 15차 부분 충돌 코드, 스타일 저장 데이터는 변경하지 않았습니다.')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        if args.check:
            changes = preflight(args.root)
            print(f'설치 전 검사 통과: {len(changes)}개 파일 수정/추가 예정')
            for change in changes:
                print(' -', change.path.relative_to(args.root.resolve()))
        else:
            install(args.root)
    except (PatchError, OSError, UnicodeError, SyntaxError, ValueError) as error:
        print('서식 개념 태그 설치 중단:', error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
