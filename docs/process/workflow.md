# 문서 관리 워크플로우

이 문서는 `series-pipeline`에서 문서를 관리하는 기본 규칙(3단계 워크플로우)을 정의합니다.

---

## 📋 워크플로우 개요

```
┌─────────────────────────────────────────────────────────┐
│         일상 작업 시 문서 관리 워크플로우                       │
└─────────────────────────────────────────────────────────┘

1️⃣ worklog 우선 (일일 작업 기록)
   ↓
   매일 작업, 발견사항, 버그 조사를 실시간 기록
   위치: docs/worklog/YYYY-MM/YYYY-MM-DD_topic.md

2️⃣ 확정되면 roadmap (공식 계획)
   ↓
   다음 버전에 포함할 기능 결정 시 업데이트
   위치: docs/planning/roadmap.md

3️⃣ 필요시 PRD/design (상세 문서)
   ↓
   복잡한 기능의 상세 스펙이나 설계 필요 시 작성
   위치: docs/planning/PRD.md 또는 docs/design/[feature]-design.md
```

---

## 🎯 핵심 원칙

1. **worklog는 일상 작업 기록** - 부담 없이 자유롭게 작성
2. **roadmap은 공식 계획** - 확정된 기능만 포함
3. **PRD/design은 상세 문서** - 복잡한 기능에 한해 작성

---

## 📝 작업별 문서 선택 가이드

| 상황 | 문서 위치 | 사용 시점 |
|------|----------|---------|
| 버그 발견 | `docs/worklog/` | 즉시 |
| 이슈 조사 | `docs/worklog/` | 조사 시작 시 |
| 기능 아이디어 | `docs/worklog/` → `docs/planning/roadmap.md` | 아이디어 → 확정 |
| 상세 스펙 | `docs/planning/PRD.md` | 기능 확정 후 |
| 복잡한 설계 | `docs/design/` | 아키텍처 영향 있을 때 |
| 릴리스 완료 | `docs/user/release-notes.md` | 버전 출시 시 |

---

## ✅ 체크리스트

### 초기 설정
- [x] docs/ 디렉토리 구조 생성
- [x] worklog/TEMPLATE.md 작성
- [x] planning/roadmap.md 초안 작성
- [x] planning/PRD.md 템플릿 작성
- [x] process/workflow.md 작성

### 일일 작업
- [ ] 매일 worklog 파일 생성 (YYYY-MM-DD_topic.md)
- [ ] 작업 시작 시 목표 작성
- [ ] 작업 중 발견사항 실시간 기록
- [ ] 작업 완료 시 상태 업데이트

### 기능 확정 시
- [ ] roadmap.md 업데이트
- [ ] 버전 및 일정 명시
- [ ] worklog 링크 추가
- [ ] 필요시 PRD 업데이트

### 설계 필요 시
- [ ] design/[feature]-design.md 생성
- [ ] 아키텍처 다이어그램 추가
- [ ] API/데이터 모델 명세
- [ ] roadmap과 링크 연결

### 릴리스 전
- [ ] user/release-notes.md 업데이트
- [ ] 모든 문서 최신화 검증
- [ ] 링크 연결 확인

---

## 🎓 사용 예시

### 예시 1: 버그 발견부터 수정까지
```markdown
1️⃣ 버그 발견 즉시
📝 docs/worklog/2026-01/2026-01-15_stage6-voiceid-bug.md 생성
   - 증상 기록
   - 재현 방법
   - 관련 코드 분석
   - 해결 방안 제시

2️⃣ 수정 확정 시
📋 docs/planning/roadmap.md 업데이트
   ## v0.1.1 (긴급 패치: 2026-01-20)
   ### 버그 수정
   - [ ] Voice ID 처리 오류 수정
     - worklog: [stage6-voiceid-bug.md](../worklog/2026-01/2026-01-15_stage6-voiceid-bug.md)

3️⃣ 릴리스 후
📖 docs/user/release-notes.md 업데이트
   ## v0.1.1 (2026-01-20)
   ### 버그 수정
   - 특정 조건에서 Voice ID가 누락되는 문제 수정
```

### 예시 2: 새 기능 아이디어부터 구현까지
```markdown
1️⃣ 아이디어 단계
📝 docs/worklog/2026-01/2026-01-16_batch-run-idea.md
   - 아이디어 배경
   - 사용자 니즈 분석
   - 기술 가능성 검토

2️⃣ 기능 확정
📋 docs/planning/roadmap.md
   ## v0.2.0 (예정: 2026-02)
   ### 주요 기능
   - [ ] 배치 실행 지원
     - worklog: [batch-run-idea.md](../worklog/2026-01/2026-01-16_batch-run-idea.md)

3️⃣ 상세 설계
📐 docs/design/batch-run-design.md
   - 입력 목록 포맷
   - 실패/재시도 정책
   - 산출물 디렉토리 정책

4️⃣ 구현 진행
📝 docs/worklog/2026-02/2026-02-05_batch-run-impl.md
   - 구현 진행 상황
   - 발생한 문제와 해결
   - 테스트 결과
```

---

## 🚨 주의사항

### DO ✅
1. **worklog는 부담 없이 작성** - 완벽하지 않아도 OK
2. **확정된 것만 roadmap에** - 불확실한 것은 worklog에만
3. **복잡한 것만 설계 문서로** - 간단한 기능은 worklog로 충분
4. **링크로 연결** - 문서 간 참조 관계 명확히

### DON'T ❌
1. **worklog를 공식 문서로 사용하지 말기**
2. **roadmap에 불확실한 것 넣지 않기**
3. **모든 기능에 설계 문서 작성하지 않기**
4. **문서 중복 작성하지 않기** - 링크로 참조

---

## 🔄 프로젝트 맞춤화

이 워크플로우를 `series-pipeline`의 특성에 맞게 다음을 조정할 수 있습니다.

1. **디렉토리 구조**: 프로젝트 규모에 맞게 간소화 또는 확장
2. **문서 템플릿**: 팀의 작업 방식에 맞게 섹션 추가/삭제
3. **우선순위 시스템**: P0/P1/P2 대신 다른 체계 사용 가능
4. **버전 명명**: 릴리스 전략에 맞게 조정

---

이 문서는 필요에 따라 업데이트하며, 변경 시 관련 worklog에 링크를 남깁니다.
