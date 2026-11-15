"""GitHub iigi71944/capstone_main 의 실제 Hook/Factory 저장 구조에 맞춘 안전 설치기.

기존 코드 파일은 ZIP에서 덮어쓰지 않고, 설치기의 사전 검증 후 최소 부분만 수정한다.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import re
import sys
import tempfile

MARK = "CAPSTONE_FORMATTING_STYLE_GIT_ALIGNED_V2"

class InstallationError(RuntimeError):
    pass

@dataclass(frozen=True)
class PlannedChange:
    path: Path
    old: bytes
    new: bytes


def _exact_once(source: str, old: str, message: str) -> str:
    if source.count(old) != 1:
        raise InstallationError(f"{message} (발견: {source.count(old)}개). 변경 없이 중단합니다.")
    return old


def _patched_route(source: str) -> tuple[str, bool]:
    if MARK in source:
        return source, False
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise InstallationError("analyze.py의 Python 구문 분석 실패") from exc
    if not any(isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "router" for t in node.targets) for node in tree.body):
        raise InstallationError("analyze.py에서 router 선언을 찾지 못했습니다.")
    if re.search(r'@router\.post\s*\(\s*["\']/formatting-style["\']', source):
        raise InstallationError("기존 /formatting-style 경로가 있습니다. 충돌 위험으로 중단합니다.")
    appendix = f'''

# {MARK}: 원본 코드 수정 없이 서식 정보만 반환합니다.
from pydantic import BaseModel as _FormattingStyleBaseModel
from app.services.style_format_profile_service import extract_formatting_style as _extract_formatting_style

class _FormattingStyleRequest(_FormattingStyleBaseModel):
    code: str

@router.post("/formatting-style")
def _analyze_formatting_style(request: _FormattingStyleRequest):
    try:
        profile = _extract_formatting_style(request.code)
    except SyntaxError:
        return {{"success": False, "formatting_style": None, "error": "Python 문법 오류가 있습니다."}}
    return {{"success": True, "formatting_style": profile}}
'''
    new = source.rstrip() + "\n" + appendix
    ast.parse(new)
    return new, True


def _patched_api(source: str) -> tuple[str, bool]:
    if MARK in source:
        return source, False
    # Git에서 확인한 기존 analyzeCode URL과 동일한 API_BASE_URL을 사용한다.
    _exact_once(source, '`${API_BASE_URL}/api/v1/analyze`', '실제 Git API 경로 확인 실패')
    if re.search(r'\b(analyzeFormattingStyle|formatting-style)\b', source):
        raise InstallationError("api.ts에 기존 서식 API가 있어 자동 변경을 중단합니다.")
    add = f'''

// {MARK}: 원래 analyzeCode와 동일 서버에 서식 분석을 요청합니다.
export async function analyzeFormattingStyle(
  code: string
): Promise<Record<string, unknown>> {{
  const response = await fetch(`${{API_BASE_URL}}/api/v1/formatting-style`, {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify({{ code }}),
  }});
  if (!response.ok) throw new Error("서식 분석 요청에 실패했습니다.");
  const data: unknown = await response.json();
  if (!data || typeof data !== "object") {{
    throw new Error("서식 분석 결과가 올바르지 않습니다.");
  }}
  const result = data as {{ success?: boolean; formatting_style?: unknown }};
  if (result.success !== true || !result.formatting_style ||
      typeof result.formatting_style !== "object" ||
      Array.isArray(result.formatting_style)) {{
    throw new Error("서식 분석이 정상적으로 완료되지 않았습니다.");
  }}
  return result.formatting_style as Record<string, unknown>;
}}
'''
    return source.rstrip() + "\n" + add, True


def _patched_hook(source: str) -> tuple[str, bool]:
    if MARK in source:
        return source, False
    _exact_once(source, 'import { analyzeCode } from "../lib/api";', 'useCodeAnalysis.ts API import 확인 실패')
    _exact_once(source, '      setIdentity(createCodingStyleIdentity());\n      setResult(data);', 'useCodeAnalysis.ts 분석 결과 저장 흐름 확인 실패')
    new = source.replace('import { analyzeCode } from "../lib/api";',
        f'// {MARK}\nimport {{ analyzeCode, analyzeFormattingStyle }} from "../lib/api";', 1)
    new = new.replace('      setIdentity(createCodingStyleIdentity());\n      setResult(data);',
        '      // 코드 분석이 성공한 경우에만 서식을 추가 분석합니다.\n'
        '      const formattingStyle = await analyzeFormattingStyle(code);\n'
        '      if (requestVersion.current !== requestId) return;\n'
        '      setIdentity(createCodingStyleIdentity());\n'
        '      setResult({ ...data, formatting_style: formattingStyle });', 1)
    return new, True


def _patched_factory(source: str) -> tuple[str, bool]:
    if MARK in source:
        return source, False
    _exact_once(source, '    metrics: analysis.metrics,', 'codingStyleFactory.ts 메트릭 저장 구문 확인 실패')
    _exact_once(source, '    created_at: options.created_at,', 'codingStyleFactory.ts 생성 날짜 저장 구문 확인 실패')
    new = source.replace('    metrics: analysis.metrics,',
        f'    metrics: analysis.metrics,\n\n    // {MARK}: 코드에서 추출한 서식 취향을 함께 저장합니다.\n'
        '    formatting_style: analysis.formatting_style,', 1)
    return new, True


def _add_type(source: str, label: str) -> str:
    # 해당 타입 내에서 metrics 다음에 선택적인 필드를 추가한다.
    match = re.search(label, source)
    if match is None:
        raise InstallationError(f"types/analysis.ts에서 {label} 타입을 찾지 못했습니다.")
    opening = source.find('{', match.start())
    closing = source.find('}', opening)
    if opening < 0 or closing < 0:
        raise InstallationError('types/analysis.ts 타입 블록을 확인하지 못했습니다.')
    segment = source[opening:closing]
    _exact_once(segment, '  metrics: Record<string, number>;', 'types/analysis.ts 메트릭 타입 확인 실패')
    if 'formatting_style' in segment:
        raise InstallationError('기존 타입에 서식 정보가 있습니다. 중복 방지를 위해 중단합니다.')
    section = segment.replace('  metrics: Record<string, number>;',
        '  metrics: Record<string, number>;\n  formatting_style?: Record<string, unknown>;', 1)
    return source[:opening] + section + source[closing:]


def _patched_types(source: str) -> tuple[str, bool]:
    if MARK in source:
        return source, False
    new = _add_type(source, r'\bexport\s+type\s+AnalysisResponse\s*=\s*\{')
    new = _add_type(new, r'\bexport\s+interface\s+CodingStyle\s*\{')
    return f'// {MARK}: 분석 및 저장 서식 프로필 타입\n' + new, True


def _normalize(data: bytes) -> tuple[str, bool, bool]:
    if data.startswith(b'\xef\xbb\xbf'):
        bom, raw = True, data[3:]
    else:
        bom, raw = False, data
    text = raw.decode('utf-8')
    crlf = text.count('\r\n') > 0 and text.count('\r\n') >= text.count('\n') / 2
    return text.replace('\r\n', '\n'), bom, crlf


def plan(project_root: Path) -> list[PlannedChange]:
    project_root = Path(project_root)
    service = project_root / 'backend/app/services/style_format_profile_service.py'
    if not service.is_file():
        raise InstallationError('기존 ZIP의 서식 분석 서비스가 없습니다. 원본 서식 ZIP을 먼저 압축 해제해야 합니다.')
    files = [
        ('backend/app/api/routes/analyze.py', _patched_route),
        ('frontend/lib/api.ts', _patched_api),
        ('frontend/hooks/useCodeAnalysis.ts', _patched_hook),
        ('frontend/lib/codingStyleFactory.ts', _patched_factory),
        ('frontend/types/analysis.ts', _patched_types),
    ]
    changes=[]
    marked_count=0
    for rel, patcher in files:
        path=project_root / rel
        if not path.is_file():
            raise InstallationError('필수 파일 없음: '+rel)
        original=path.read_bytes()
        source,bom,crlf=_normalize(original)
        if MARK in source: marked_count+=1
        new, changed=patcher(source)
        if changed:
            if crlf: new=new.replace('\n','\r\n')
            payload=(b'\xef\xbb\xbf' if bom else b'') + new.encode('utf-8')
            changes.append(PlannedChange(path, original, payload))
    if 0 < marked_count < len(files):
        raise InstallationError('이전 설치가 일부 파일에만 적용되어 있습니다. 자동 변경을 중단합니다.')
    return changes


def install(root: Path, backup_root: Path | None = None) -> list[str]:
    root=Path(root)
    changes=plan(root)  # 사전 검증 통과 이후에만 수정
    if not changes:
        return ['이미 연결되어 있어 파일을 변경하지 않았습니다.']
    if backup_root is None:
        git=root/'.git'
        base=git/'capstone_formatting_git_aligned_backup' if git.is_dir() else Path(tempfile.mkdtemp(prefix='capstone_formatting_backup_'))
        backup_root=base
    backup_root=Path(backup_root)
    for item in changes:
        dest=backup_root/item.path.relative_to(root)
        dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():
            raise InstallationError('기존 백업 파일을 덮어쓰지 않습니다: '+str(dest))
        dest.write_bytes(item.old)
    written=[]
    try:
        for item in changes:
            item.path.write_bytes(item.new)
            written.append(item)
    except BaseException:
        for item in written:
            item.path.write_bytes(item.old)
        raise
    return [str(c.path.relative_to(root)) for c in changes]+['backup: '+str(backup_root)]


def main() -> int:
    root=Path(__file__).resolve().parents[2]
    check_only = len(sys.argv) == 2 and sys.argv[1] == "--check"
    if len(sys.argv) > 1 and not check_only:
        print("사용법: python backend/tools/install_formatting_style.py [--check]")
        return 2
    try:
        if check_only:
            changes = plan(root)
            if changes:
                for item in changes:
                    print("[사전 검사 정상] " + str(item.path.relative_to(root)))
                print("[사전 검사 완료] 아직 원본 파일을 수정하지 않았습니다.")
            else:
                print("[사전 검사 완료] 이미 설치되어 있습니다.")
            return 0
        messages=install(root)
    except (InstallationError, OSError, UnicodeError) as exc:
        print('[설치 중단] '+str(exc))
        return 1
    for m in messages: print('[완료] '+m)
    return 0

if __name__=='__main__':
    sys.exit(main())
