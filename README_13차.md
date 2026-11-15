# 캡스톤 디자인 자동 변환 13차 패치

기준 GitHub 커밋: `b89bcc82955e3ee781ecbd7d4a0bcd2875f5bc50` (`main`)

## 개발 내용

- 신규 연결 3개: `문자열 리터럴`, `숫자 리터럴`, `불리언 리터럴`
- 새 함수의 변환 대상을 **내장 `str()` / `str(None|True|False)`, `int()` / `int(True|False)`, `bool()` / `bool(None|0|1)`** 로 제한합니다.
- Python AST로 검사하고 해당 호출 범위의 원문 바이트만 교체합니다. 그 외 주석, CRLF/LF, 한글 텍스트는 유지합니다.
- `str` / `int` / `bool` 재정의, import 문, 동적 전역 접근과 실행이 보이면 변환하지 않습니다. 기존과 동일하게 런타임 검증을 거칩니다. 이 제한적 검사는 임의의 프로그램에 대한 완전한 의미 동등성 증명은 아닙니다.
- 저장된 메트릭 중 `string_literal_count`, `number_literal_count`, `boolean_literal_count`, `call_count`만 사용합니다. 저장 포맷, API, UI는 변경하지 않습니다.
- 12차 통합 테스트의 고정 태그 개수 75 검사를 **12차 연결 유지 및 집합 일관성 검사**로 수정합니다. 또한 12차 감사 스크립트를 이후 신규 태그를 허용하는 검증 기준으로 조정합니다. (11차 호환 테스트는 이미 12차에서 수정되었습니다.)
- 태그가 `missing_syntax_tags`에 들어왔다는 이유만으로 새 변환을 실행하지 않습니다. 저장된 메트릭 조건을 충족할 때에만 실행합니다.

## PowerShell 설치 절차

ZIP을 `capstone_main` 루트(현재 `docker-compose.yml`이 있는 경로)에 놓으신 뒤 **PowerShell**에서:

```powershell
Expand-Archive -LiteralPath ".\capstone_batch13_20261116.zip" -DestinationPath "." -Force
python backend\tools\install_unmapped_batch13.py --check
python backend\tools\install_unmapped_batch13.py
```

사전 검사 실패 시 설치하지 말고 실패 메시지를 전달해 주세요. 기준 소스에 변경이 있을 때 기존 파일을 강제로 덮어쓰지 않도록 설계했습니다. 수정 전 버전은 `.git\capstone_batch13_backups`에 저장됩니다.

## 검증

```powershell
docker compose run --rm backend python -m unittest discover -s tests -p "test_*.py"
docker compose run --rm backend python tools/audit_transform_three_patterns_batch13.py --output transform_audit_batch13.json
```

**적용 후 목표**: 102개 태그 중 연결 78개, 비교 전용 24개, 대표 검사 234/234.

**예상 전체 단위 테스트 수**: 이전 1,634개 + 새 25개 = 약 1,659개. 실제 실행 결과를 기준으로 판단해 주세요.

### 다른 버전이거나 설치 실패한 경우

- `--check`에서 기존 소스 해시, 연결 개수 또는 새 파일 충돌이 감지되면 설치를 멈춥니다.
- 사용자 수정 사항을 무조건 교체하는 `-Force` 패치는 사용하지 않습니다. `Expand-Archive -Force`는 배포된 **패치 설치 도구 파일**을 푸는 작업이며, 설치 도구가 기존 소스 수정을 사전 검사합니다.
- Git으로 관리하는 다른 작업을 진행 중이라면 먼저 커밋하거나 작업 내용을 보존해 주세요.
- 백업에는 기존 파일만 들어가며, 신규 파일 4개는 테스트 실패 후 필요에 따라 삭제 가능합니다.

## 파일 변경 목록

기존 파일 수정 (5개):
- `backend/app/services/style_tag_transform_map_service.py`
- `backend/app/services/style_apply_service.py`
- `backend/app/services/style_transform_plan_service.py`
- `backend/tests/test_style_unmapped_patterns_batch12_integration.py`
- `backend/tools/audit_transform_three_patterns_batch12.py`

신규 파일 (4개):
- `backend/app/services/improvement/safe_unmapped_patterns_batch13_service.py`
- `backend/tests/test_style_unmapped_patterns_batch13.py`
- `backend/tests/test_style_unmapped_patterns_batch13_integration.py`
- `backend/tools/audit_transform_three_patterns_batch13.py`

패키지에는 위 작업을 수행할 `backend/tools/install_unmapped_batch13.py` 및 SHA256으로 무결성 확인되는 신규 파일 원본이 포함되어 있습니다.

## 검증 범위의 한계

개발 환경에서 새 변환기 테스트 17개, 설치 도구 관련 모의 테스트 4개, 감사기 모의 테스트를 수행했습니다. 사용자 프로젝트의 Docker 환경에서 전체 1,659개 예상 테스트와 234개 대표 검증을 실행하는 단계는 아직 남아 있습니다. **Docker 실행 결과를 확인하기 전에는 전체 회귀 테스트 통과라고 표시하지 않습니다.**
