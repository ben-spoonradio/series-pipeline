# Project Plan

프로젝트: **series-pipeline**

**마지막 업데이트**: 2026-01-13

---

## 목표
- 텍스트 기반 소스 파일을 오디오 컨텐츠 제작 파이프라인으로 변환한다.
- 스테이지별 산출물/검수/재실행이 가능한 운영-friendly 구조를 유지한다.

## 범위
- 포함: 스테이지 0~7(2a/3a/6a 포함), 리뷰 출력, QA 리포트
- 제외: 웹 UI(요구 시 별도 로드맵으로 관리)

## 산출물(대표)
- `processed/<lang_code>/<publisher>/<series_name>/...` 하위 스테이지 산출물
- `pipeline_qa_report.md/.json`

## 리스크/의존성
- 외부 API 의존: Gemini(Qwen/Ollama), ElevenLabs(TTS)
- 로컬 의존: FFmpeg(오디오 처리), Python 패키지
- 운영 리스크: 비용/레이트리밋/차단(safety)

## 운영 원칙
- 모든 작업은 `docs/worklog/`에 기록 후, 확정되면 `roadmap.md`로 승격
- 민감정보(API 키)는 `.env`에만 저장하고 커밋 금지
