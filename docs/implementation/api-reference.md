# CLI / API Reference

이 프로젝트는 HTTP API가 아니라 **CLI 기반 파이프라인**입니다.

---

## `pipeline.py`

### 기본 사용
```bash
python pipeline.py "<source_file>"
```

### 주요 옵션
- `--auto`: 사람 개입 없이 자동 진행
- `--skip-stages`: 콤마 구분 스테이지 스킵(예: `2a,3a,6a` 또는 `5,6,6a,7`)
- `--rate-limit`: auto 모드에서 API 호출 간격(초)
- `--qa-report`: 실행 종료 시 QA 리포트 생성
- `--stop-on-error`: auto 모드에서 실패 시 즉시 종료
- `--max-episodes`: TTS/오디오 스테이지에서 에피소드 수 제한
- `--master`, `--peak-db`, `--rms-db`: Stage 7 마스터링
- `--review-output`: `_review/`에 리뷰용 산출물 생성
- `--review-output-dir`: 리뷰 출력 위치 지정
- `--use-preset-audio`: CSV/메타데이터 기반 voice_id와 기존 music 사용
- `--langs`: 처리 언어 제한(예: `korean,japanese`)

---

## Stage 스크립트

스테이지는 단독 실행도 가능합니다.

- `stage_00_prepare.py`: 파일 변환 + 메타데이터 매칭
- `stage_01_split.py`: 에피소드 분할
- `stage_02_translate.py`: 번역
- `stage_02a_translation_qa.py`: 번역 QA
- `stage_03_format.py`: TTS 포맷팅
- `stage_03a_speaker_tagging.py`: 화자 태깅
- `stage_04_tag_emotions.py`: 감정 태깅
- `stage_05_setup_audio.py`: 오디오 설정/보이스 디자인
- `stage_06_generate_tts.py`: TTS 생성
- `stage_06a_tts_qa.py`: TTS QA
- `stage_07_mix_audio.py`: 믹싱/마스터링

---

## 환경 변수

### LLM
- `GEMINI_API_KEY`
- `LLM_MODEL` (`gemini` 기본, `qwen` 지원)
- `OLLAMA_API_KEY`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`

### TTS
- `ELEVENLABS_API_KEY`

### 경로
- `SERIES_SOURCE_DIR`, `SERIES_OUTPUT_DIR`, `SERIES_REVIEW_DIR`, `SERIES_DATA_DIR`
