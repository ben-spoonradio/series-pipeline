# Test Cases

**목표**: `pipeline.py` 및 각 스테이지의 기본 동작을 수동/반자동으로 검증합니다.

---

## 사전 준비
- `.env`에 최소한 `GEMINI_API_KEY` 또는 `LLM_MODEL=qwen`+`OLLAMA_API_KEY` 설정
- TTS/오디오 단계까지 검증하려면 `ELEVENLABS_API_KEY` 및 FFmpeg 권장

---

## TC-01: Stage 0 산출물 생성
1. 입력 파일 하나 준비(DOCX/PDF/TXT/HWP)
2. 실행: `python stage_00_prepare.py "<source_file>"`
3. 기대 결과:
   - `processed/<lang_code>/<publisher>/<series_name>/series_metadata.json` 생성
   - `series_metadata.json`에 `source_language` 포함

## TC-02: 파이프라인 텍스트 단계(0~4) Auto 스모크
1. 실행: `python pipeline.py "<source_file>" --auto --skip-stages 5,6,6a,7 --qa-report`
2. 기대 결과:
   - Stage 0~4(2a/3a 포함 여부는 구현/옵션에 따름) 관련 폴더 생성
   - `pipeline_qa_report.md` 생성

## TC-03: 리뷰 출력 생성
1. 실행: `python pipeline.py "<source_file>" --auto --review-output --skip-stages 5,6,6a,7`
2. 기대 결과:
   - `_review/`에 사람이 보기 쉬운 산출물이 생성됨

## TC-04: Stage 5 preset 모드
1. 전제: `series_metadata.json`에 `default_voice_id` 또는 `default_voice_id_jp` 존재 + `music/`에 음악 파일 존재(선택)
2. 실행: `python pipeline.py "<source_file>" --auto --use-preset-audio --skip-stages 6,6a,7`
3. 기대 결과:
   - `05_audio_setup/<lang>/audio_config.json` 생성

## TC-05: Stage 6 TTS 생성(언어 1개)
1. 전제: Stage 4 완료 + `05_audio_setup/<lang>/audio_config.json` 존재
2. 실행: `python stage_06_generate_tts.py "<series_folder>" --lang korean --max-episodes 1`
3. 기대 결과:
   - `06_tts_audio/korean/episode_001/`에 mp3 chunk 생성

## TC-06: Stage 7 믹싱(voice-only)
1. 전제: Stage 6 완료
2. 실행: `python stage_07_mix_audio.py "<series_folder>" --lang korean --max-episodes 1`
3. 기대 결과:
   - `07_final_audio/korean/`에 `episode_001_final.mp3` 생성

---

## 관찰 포인트
- LLM 응답 차단/품질 문제는 `stage_XX_*.log`와 QA 리포트에 기록
- 재실행 시 기존 산출물 처리 정책(스킵/재생성)이 일관적인지 확인
