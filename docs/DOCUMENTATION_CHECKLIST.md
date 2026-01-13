# Documentation Checklist

프로젝트: **series-pipeline – 멀티언어 번역/TTS/오디오 믹싱 파이프라인**  
작성일: 2026-01-13  
최종 업데이트: 2026-01-13

---

## 📋 문서 작업 진행 현황

### 범례
- ⬜ 작업 예정
- 🔄 작업 중
- ✅ 완료
- ⏸️ 보류
- ❌ 해당 없음

---

## 프로젝트 개요

### 기본 정보
- **프로젝트명**: series-pipeline
- **형태**: CLI 기반 파일 파이프라인 (`pipeline.py` + `stage_*.py`)
- **언어**: Python
- **핵심 의존**:
  - LLM: Gemini(`google-generativeai`) 또는 Qwen(Ollama API)
  - TTS: ElevenLabs
  - Audio: FFmpeg(권장) + pydub

### 핵심 기능(현재 코드 기준)
- Stage 0~7 오케스트레이션(2a/3a/6a 포함)
- `--auto`, `--skip-stages`, `--qa-report`, `--review-output` 지원
- 경로 자동 탐지/환경변수 오버라이드(`config.py`)

---

## 1. Worklog (1단계)

📁 위치: `docs/worklog/`

| 상태 | 문서명 | 파일명 | 비고 |
|------|--------|--------|------|
| ✅ | Worklog 안내 | `docs/worklog/README.md` | 규칙/원칙 |
| ✅ | Worklog 템플릿 | `docs/worklog/TEMPLATE.md` | 일일 기록 템플릿 |
| ✅ | 월별 디렉토리 | `docs/worklog/2026-01/` | 초기 월 생성 |
| ✅ | 초기 기록 | `docs/worklog/2026-01/2026-01-13_documentation-setup.md` | 문서 체계 구축 로그 |

---

## 2. Planning (2단계)

📁 위치: `docs/planning/`

| 상태 | 문서명 | 파일명 | 비고 |
|------|--------|--------|------|
| ✅ | Planning 안내 | `docs/planning/README.md` | 문서 운영 원칙 |
| ✅ | 프로젝트 로드맵 | `docs/planning/roadmap.md` | 버전/범위 |
| ✅ | PRD 템플릿/초안 | `docs/planning/PRD.md` | 요구사항/수용 기준 |
| ✅ | 프로젝트 계획 | `docs/planning/project-plan.md` | 목표/범위/리스크 |

---

## 3. Design (3단계)

📁 위치: `docs/design/`

| 상태 | 문서명 | 파일명 | 비고 |
|------|--------|--------|------|
| ✅ | Design 안내 | `docs/design/README.md` | 설계 문서 운영 |
| ✅ | 전체 아키텍처 | `docs/design/architecture.md` | 스테이지/데이터 흐름 |
| ⬜ | 기능별 설계 템플릿 | `docs/design/[feature]-design.md` | 필요 시 생성 |

---

## 4. Implementation

📁 위치: `docs/implementation/`

| 상태 | 문서명 | 파일명 | 비고 |
|------|--------|--------|------|
| ✅ | Implementation 안내 | `docs/implementation/README.md` | 가이드 링크 |
| ✅ | 개발자 가이드 | `docs/implementation/developer-guide.md` | 설치/실행/환경변수 |
| ✅ | CLI 레퍼런스 | `docs/implementation/api-reference.md` | 옵션/환경변수 |

---

## 5. QA

📁 위치: `docs/qa/`

| 상태 | 문서명 | 파일명 | 비고 |
|------|--------|--------|------|
| ✅ | QA 안내 | `docs/qa/README.md` | 품질 문서 |
| ✅ | 테스트 케이스 | `docs/qa/test-cases.md` | 스모크/수동 테스트 |
| ⬜ | 테스트 전략 | `docs/qa/testing-strategy.md` | 필요 시 추가 |

---

## 6. User

📁 위치: `docs/user/`

| 상태 | 문서명 | 파일명 | 비고 |
|------|--------|--------|------|
| ✅ | User 안내 | `docs/user/README.md` | 사용자 문서 |
| ✅ | 사용자 매뉴얼 | `docs/user/user-manual.md` | 실행/산출물 확인 |
| ✅ | 릴리스 노트 | `docs/user/release-notes.md` | 변경 내역 |
| ⬜ | 트러블슈팅 | `docs/user/troubleshooting.md` | 필요 시 추가 |

---

## 7. Process

📁 위치: `docs/process/`

| 상태 | 문서명 | 파일명 | 비고 |
|------|--------|--------|------|
| ✅ | Process 안내 | `docs/process/README.md` | 프로세스 문서 |
| ✅ | 워크플로우 가이드 | `docs/process/workflow.md` | 3단계 워크플로우 전체 |
| ✅ | 기여 가이드 | `docs/process/contributing-guide.md` | 코드/문서 규칙 |

---

## 📊 전체 진행률 (현재)

- 필수 문서(구조/템플릿/핵심 가이드): **✅ 완료**
- 선택 문서(전략/트러블슈팅/기능 설계 템플릿): **⬜ 예정**

대략 진행률(필수 항목 기준): **100%**

---

## 🎯 다음 단계 제안

1. 샘플 입력으로 `TC-02`(텍스트 단계 스모크) 실행 후 결과를 worklog에 기록
2. `docs/user/troubleshooting.md` 추가(키 누락/FFmpeg/레이트리밋/차단 케이스)
3. 스테이지 산출물 JSON 스키마를 문서화(향후 설계 문서로 분리)
