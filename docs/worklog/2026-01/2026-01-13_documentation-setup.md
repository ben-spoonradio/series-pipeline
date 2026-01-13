# 문서 체계(Workflow) 구축

**날짜**: 2026-01-13  
**작성자**: (작성자 기입)  
**상태**: ✅ 완료

---

## 🎯 목표
- `series-pipeline`에 문서 운영 워크플로우(Worklog → Roadmap → PRD/Design)를 도입

## 📋 작업 내용
- [x] `docs/` 디렉토리 구조 생성
- [x] worklog 템플릿 작성
- [x] roadmap/PRD 템플릿 생성
- [x] 워크플로우 가이드(`docs/process/workflow.md`) 작성
- [x] 개발자/사용자/QA 기본 문서 초안 작성

## 🔍 주요 발견사항
- 파이프라인은 `pipeline.py`가 `stage_*.py` 실행을 오케스트레이션하며, 스테이지별 산출물 디렉토리 규약이 핵심
- 외부 API(LLM/TTS) 키 관리와 레이트리밋/비용 관리가 운영 리스크

## 💡 주요 결정사항
- 운영 원칙: 아이디어/조사는 worklog, 확정은 roadmap, 복잡한 변경은 PRD/design

## 📂 관련 파일/코드
- `docs/process/workflow.md`
- `docs/planning/roadmap.md`
- `docs/planning/PRD.md`
- `docs/design/architecture.md`

## 🚀 다음 단계
- 문서 간 링크 정합성 점검
- 실제 샘플 입력으로 TC 스모크 수행 후 worklog에 결과 기록

## 🔗 관련 링크
- (추가 예정)
