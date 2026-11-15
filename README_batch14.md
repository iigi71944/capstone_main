# 캡스톤 14차 — 자동 변환 액션 충돌 및 검증 상태 개선

기준: GitHub `iigi71944/capstone_main`, `main`, 커밋 `f6b7d8cba6ee71efc84f1bd0ab3588b2737c8eea`.

## 기능

- **중간 원상복원 감지**: A → B → A → C처럼 중간 두 액션이 서로 취소하고 마지막 액션만 남는 경우, 과거 액션을 최종 적용 성공으로 기록하지 않습니다.
- **반환 상태 정합성**: 런타임 검증기가 `status='different'` 와 `equivalent=True` 또는 `None`을 함께 반환하면 모순된 결과로 보고, 변경 코드를 원본으로 복원하고 `not_verified`로 표시합니다.
- **기존 계약 보존**: 스타일 API의 6개 반환값, 102개 태그, 78개 연결, 비교 전용 24개, 저장 형식과 프론트엔드 구조에 변경이 없습니다.

**한계**: 중간 액션이 직전의 코드 상태를 *완전히* 되돌린 경우만 감지합니다. 서로 다른 영역을 부분적으로 덮어쓰는 모든 의미적 충돌을 탐지한다는 주장은 하지 않습니다. 기존 런타임 검증기는 일반 사용자 코드를 안전하게 격리하는 샌드박스가 아닙니다.

## 패치 구성

- `backend/tools/install_action_conflict_batch14.py` : 사전 검사, 원본 백업, 설치 및 복원
- `backend/tools/batch14_payload/style_action_conflict_service.py.source` : 순수 충돌 집계 서비스
- `backend/tools/batch14_payload/test_style_action_conflict_batch14.py.source` : 추가 16개 테스트
- `backend/tools/batch14_payload/audit_transform_runtime_batch14.py.source` : 13차 대표 검사 + 14차 충돌 감사

설치 도구는 `backend/app/services/style_apply_service.py` 1개를 수정하고, 위의 `.source` 파일을 실행용 `.py` 파일 3개로 복사합니다. 기존 파일이 변형되었다면 **중단**하며 덮어쓰지 않습니다. 설치 전 Git blob과 payload SHA256을 검사하고 CRLF/BOM을 보존합니다. 수정된 기존 파일은 `.git/capstone_batch14_backups/`에 보관합니다.

## Windows PowerShell

프로젝트 루트 `capstone_main`에 ZIP 파일을 놓고 실행합니다.

```powershell
Expand-Archive -LiteralPath ".\capstone_batch14_20261116.zip" -DestinationPath "." -Force
python backend\tools\install_action_conflict_batch14.py --check
python backend\tools\install_action_conflict_batch14.py
```

설치 전 검사에서 4개 수정/추가 예정이 나와야 합니다. 충돌 또는 버전 불일치가 나오면 설치를 하지 말고 오류 메시지를 확인하세요.

```powershell
docker compose run --rm backend python -m unittest discover -s tests -p "test_*.py"
docker compose run --rm backend python tools/audit_transform_runtime_batch14.py --output transform_runtime_audit_batch14.json
```

예상 검증 목표:

- 전체 테스트: **1,675건 통과** (기존 1,659 + 신규 16)
- 태그: 전체 102 / 연결 78 / 비교 전용 24
- 이전 3종 대표 검사: **234/234 통과**
- 14차 충돌·검증 신규 테스트: **16/16 통과**

이 수치는 **사용자 환경에서 확인할 목표값**입니다. 이 패키지는 로컬 모의 서비스에서 신규 시나리오 16건과 설치 안전성 7건을 검사했지만, 실제 GitHub 프로젝트 전체 테스트를 이 환경에서 실행한 것은 아닙니다.

## 적용 후 Git 상태 확인

```powershell
git status
git diff --stat
```

검사가 끝나기 전에는 Push하지 마세요.
