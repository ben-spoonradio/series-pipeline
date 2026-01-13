# Developer Guide

**프로젝트**: `series-pipeline` (Python 기반 파일 파이프라인)

---

## 1) 환경 설정

### Python
- Python 3.x 환경에서 실행 (패키지 의존: `requirements.txt`)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 필수/권장 도구
- FFmpeg (Stage 7 믹싱/마스터링에서 권장)

---

## 2) 환경 변수(.env)

`.env`는 커밋하지 않습니다(이미 `.gitignore` 처리됨).

### 경로 설정(선택)
- `SERIES_SOURCE_DIR`: 소스 폴더
- `SERIES_OUTPUT_DIR`: 출력 폴더
- `SERIES_REVIEW_DIR`: 리뷰 폴더(없으면 output 아래로)
- `SERIES_DATA_DIR`: `IP_LIST.csv` 등 데이터 폴더

### API 키
- `GEMINI_API_KEY`: 기본 LLM(번역/태깅/포맷팅)
- (대안) `LLM_MODEL=qwen`, `OLLAMA_API_KEY`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`
- `ELEVENLABS_API_KEY`: TTS/보이스 디자인

---

## 3) 실행 방법

### 전체 파이프라인
```bash
python pipeline.py "<source_file>"
```

### Auto 모드(권장: 대량 처리 시)
```bash
python pipeline.py "<source_file>" --auto --qa-report
```

### 텍스트 처리만(오디오 단계 스킵)
```bash
python pipeline.py "<source_file>" --auto --skip-stages 5,6,6a,7
```

### 리뷰 출력(사람이 보기 좋은 산출물)
```bash
python pipeline.py "<source_file>" --auto --review-output
```

---

## 4) 출력 구조 이해

출력은 보통 아래 형태입니다.

- `processed/<language_code>/<publisher>/<series_name>/`
  - `01_split/`
  - `02_translated/{korean,japanese,taiwanese}/`
  - `02a_qa_report/`
  - `03_formatted/{lang}/`
  - `03a_speaker_tagged/{lang}/`
  - `04_tagged/{lang}/`
  - `05_audio_setup/{lang}/audio_config.json`
  - `06_tts_audio/{lang}/episode_###/`
  - `06a_tts_qa_report/`
  - `07_final_audio/{lang}/`

---

## 5) 개발/품질

- 포맷팅: `black`
- 린트: `flake8`
- 테스트: `pytest`

```bash
pytest
black .
flake8
```
