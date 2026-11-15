12차 패치 이후 발생한 11차 고정 태그 수 테스트 충돌 수정

원인:
11차 통합 테스트에서 72개/30개를 고정 기대했지만, 12차 적용 후 75개/27개가 정상입니다.

사용법 (capstone_main 프로젝트 최상위 폴더에서):
1. Expand-Archive -LiteralPath ".\capstone_batch12_legacy_test_fix.zip" -DestinationPath "." -Force
2. python backend\tools\fix_batch12_legacy_test.py --check
3. python backend\tools\fix_batch12_legacy_test.py
4. docker compose run --rm backend python -m unittest discover -s tests -p "test_*.py"
5. docker compose run --rm backend python tools/audit_transform_three_patterns_batch12.py --output transform_audit_batch12.json

수정 범위: backend/tests/test_style_unmapped_patterns_batch11_integration.py 의 검증 함수 1개
- 문법 태그 등록 중복 검사 유지
- 최소 72개 연결 태그 불변성 검사 유지
- 연결/비교전용 집합이 실제 태그 규칙 102개와 일치하는지 검사
- 12차의 정확한 75개/27개 검사는 12차 테스트와 전수 검사에서 별도로 수행

재실행해도 중복 수정하지 않습니다. 기존 파일 백업은 .git 폴더에 저장됩니다.
