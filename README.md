# JJAJUKA AI Server

> 자연어 요청을 실제 근무표로 변환하는  
> **LLM + OR-Tools + LangGraph 기반 AI 워크플로우 서버**

---

## 🧠 핵심 개념: Prompt Chaining + State Flow

이 서버는 하나의 LLM 호출로 결과를 만들지 않습니다.

작업을 여러 단계로 나누고,  
각 단계의 결과(State)를 다음 단계로 전달하는 구조를 사용합니다.

```
자연어 입력
 → LLM 파싱
 → 제약 생성 (constraints / instructions)
 → OR-Tools Solver
 → 결과 + 메타 데이터
 → LLM 설명 생성
```

---

## ⚙️ 전체 처리 흐름

```
user_request
 → LLM parser (또는 fallback parser)
 → 구조화 제약 (instructions)
 → input_json에 merge
 → solver 파라미터 추출
 → OR-Tools CP-SAT 실행
 → 스케줄 생성
 → 결과 설명 (LLM 또는 template)
```

---

## 🎯 핵심 아이디어

자연어를 바로 solver에 넣지 않습니다.

```
자연어 → constraint catalog → solver
```

### 장점
- 요청 반영 여부 추적 가능
- 무시된 요청 확인 가능
- LLM 실패 시 fallback 가능
- 설명과 계산 분리

---

## ✨ 주요 기능

- 자연어 기반 근무표 생성
- constraint catalog 기반 파싱
- OR-Tools 최적화 스케줄링
- 야간/주말 공정성 최적화
- LLM 설명 생성 + fallback
- 대체 인력 추천 API

---

## 🧩 지원되는 자연어 예시

| 요청 | 변환 | 설명 |
|------|------|------|
| 김민지 쉬게 | ADD_OFFDAY | 휴무일 |
| Night 금지 | FORBID_SHIFT | 시프트 제한 |
| 하루 1개만 | SET_MAX_SHIFTS_PER_DAY | 전역 제한 |
| 야간 공평 | BOOST_NIGHT_FAIRNESS | 가중치 |

---

## ⚠️ 지원하지 않는 요청

- 분위기 좋게
- 인간적으로
- 잘 맞는 사람

→ parserWarnings 처리

---

## 🔁 Fallback 전략

- parser 실패 → fallback parser
- explanation 실패 → template
- API 키 없음 → 전체 fallback

---

## 📡 API 역할

이 서버는 JJAJUKA 시스템에서 **AI 처리 전용 서버**입니다.

- 자연어 처리
- 스케줄 생성
- 설명 생성
- 추천 기능

---

## 🚀 실행

```
pip install -r requirements.txt
uvicorn main:app --reload
```

---

## 📁 구조

```
features/scheduling/
  parser.py
  merge.py
  solver.py
  explain.py
```

---

## 🧠 요약

LLM(이해) + OR-Tools(계산) + LangGraph(흐름)

→ 상태 기반 AI 워크플로우 시스템
