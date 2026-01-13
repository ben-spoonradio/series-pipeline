# Contributing Guide

## 브랜치/커밋
- 작은 단위로 커밋하고, 커밋 메시지는 변경 의도를 드러내세요.
- 민감정보(.env, 키/토큰/개인정보)는 절대 커밋하지 않습니다.

## 코드 스타일
- Python 포맷: `black`
- 린트: `flake8`
- 테스트: `pytest`

## 문서 작업
- 일상 작업은 `docs/worklog/`에 먼저 기록
- 확정된 계획은 `docs/planning/roadmap.md` 업데이트
- 복잡한 변경은 `docs/planning/PRD.md` 또는 `docs/design/`에 설계 문서 추가

## PR 체크리스트(권장)
- [ ] 관련 worklog 링크 추가
- [ ] 새/변경 기능이 roadmap/PRD/design에 반영됐는지 확인
- [ ] `.env` 등 민감파일이 포함되지 않았는지 확인
