# Architecture

`series-pipeline`은 파일 기반 파이프라인입니다.

- 오케스트레이터: `pipeline.py`
- 스테이지 스크립트: `stage_00_prepare.py` ~ `stage_07_mix_audio.py` (+ `2a/3a/6a`)
- 공용 로직: `processors/`
- 경로/환경 설정: `config.py`

---

## 핵심 개념

### 1) 입력/출력 디렉토리
- 입력(Source): `Config.get_source_dir()` (기본: Google Drive 자동 탐지 → `_SOURCE`, 실패 시 로컬 `origin/`)
- 출력(Processed): `Config.get_output_dir()` (기본: Google Drive 자동 탐지 → `_PROCESSED`, 실패 시 로컬 `processed/`)
- 메타데이터 CSV: 기본 `IP_LIST.csv`를 Google Drive 또는 로컬 `data/`에서 로드

관련 코드:
- `config.py`
- `processors/series_metadata_matcher.py`

### 2) 스테이지 오케스트레이션
`pipeline.py`는 다음을 수행합니다.
- 스테이지 실행/로그 수집
- `--auto` 시 사람 개입 없이 진행
- 기존 산출물 감지 시 스킵/재실행 선택
- `--qa-report`로 실행 요약 리포트 생성
- `--review-output`로 사람이 읽기 쉬운 리뷰 파일 생성 + 역동기화

---

## Stage Map (요약)

- Stage 0: 파일 변환 + 메타데이터 매칭 + 소스 언어 감지
  - 산출물: `series_metadata.json`, (변환 텍스트 파일 등)
- Stage 1: 에피소드 분할
  - 산출물: `01_split/*.json`
- Stage 2: 번역(기본 3개 언어)
  - 산출물: `02_translated/{korean,japanese,taiwanese}/episode_*.json`
- Stage 2a: 번역 QA
  - 산출물: `02a_qa_report/qa_report.json`
- Stage 3: TTS 포맷팅
  - 산출물: `03_formatted/{lang}/episode_*.json`
- Stage 3a: 화자 태깅
  - 산출물: `03a_speaker_tagged/{lang}/episode_*.json`
- Stage 4: 감정 태깅
  - 산출물: `04_tagged/{lang}/episode_*.json`
- Stage 5: 오디오 설정
  - 산출물: `05_audio_setup/{lang}/audio_config.json`
- Stage 6: TTS 생성
  - 산출물: `06_tts_audio/{lang}/episode_###/*` (mp3 chunks + metadata.json)
- Stage 6a: TTS QA
  - 산출물: `06a_tts_qa_report/qa_report.json`
- Stage 7: 믹싱/마스터링
  - 산출물: `07_final_audio/{lang}/*.mp3`

---

## 데이터 흐름(개략)

```mermaid
flowchart LR
  A[Source file] --> B[Stage 0 prepare]
  B --> C[Stage 1 split]
  C --> D[Stage 2 translate]
  D --> E[Stage 2a translation QA]
  E --> F[Stage 3 format]
  F --> G[Stage 3a speaker tagging]
  G --> H[Stage 4 emotion tagging]
  H --> I[Stage 5 audio setup]
  I --> J[Stage 6 TTS]
  J --> K[Stage 6a TTS QA]
  K --> L[Stage 7 mix/master]
```

---

## 외부 의존
- LLM: Gemini(`GEMINI_API_KEY`) 또는 Ollama API(`OLLAMA_API_KEY`)
- TTS: ElevenLabs(`ELEVENLABS_API_KEY`)
- 오디오: FFmpeg(권장) + `pydub`
