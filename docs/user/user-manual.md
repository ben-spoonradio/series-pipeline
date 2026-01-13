# User Manual

`series-pipeline`은 소스 파일을 오디오 컨텐츠 산출물로 만드는 단계별 파이프라인입니다.

---

## 빠른 시작

### 1) 의존성 설치
```bash
pip install -r requirements.txt
```

### 2) `.env` 설정
- 최소: `GEMINI_API_KEY`
- 오디오까지: `ELEVENLABS_API_KEY` + FFmpeg 권장

### 3) 실행
```bash
python pipeline.py "<source_file>" --auto --qa-report
```

---

## 사용 시나리오

### 텍스트 처리만(번역/태깅까지)
```bash
python pipeline.py "<source_file>" --auto --skip-stages 5,6,6a,7
```

### 리뷰 파일 생성(사람 검수용)
```bash
python pipeline.py "<source_file>" --auto --review-output
```

### 오디오 생성까지(샘플)
```bash
python pipeline.py "<source_file>" --auto --max-episodes 1
```

---

## 결과물 확인

파이프라인은 시리즈 폴더 아래에 스테이지별 산출물을 생성합니다.

- `.../01_split/`: 에피소드 분할 JSON
- `.../02_translated/<lang>/`: 번역 결과
- `.../04_tagged/<lang>/`: 감정 태깅 결과
- `.../06_tts_audio/<lang>/`: TTS chunk
- `.../07_final_audio/<lang>/`: 최종 mp3

문제 발생 시:
- 로그: `stage_XX_*.log`
- QA: `pipeline_qa_report.md`(옵션)
