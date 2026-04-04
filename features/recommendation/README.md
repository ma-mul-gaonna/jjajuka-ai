# recommendation/service.py

월간 근무표 + 결원 정보 + 생성 당시 규칙을 받아서 대체 인력 후보를 추천하는 서비스입니다.

## 입력 payload 구조

```python
{
  "schedule": {
    "assignments": [
      {
        "assignmentId": 1,
        "date": "2026-04-12",
        "userId": 101,
        "userName": "김민지",
        "shiftName": "Night",
        "startTime": "23:00",
        "endTime": "07:00"
      }
    ]
  },
  "vacancy": {
    "assignmentId": 1,
    "date": "2026-04-12",
    "shiftName": "Night",
    "userId": 101
  },
  "rules": {
    "minRestHours": 11,
    "maxConsecutiveDays": 5
  },
  "employees": [...],
  "shifts": [...]
}
```

## 검증 규칙

- 휴무일 제외
- availableShifts 제외
- requiredRoles / requiredSkills 확인
- 같은 날짜 중복 배정 금지
- 이전/다음 배정과 최소 휴식시간 위반 금지
- maxAssignments 초과 금지
- maxConsecutiveDays 초과 금지

## 설명 생성

기본값은 템플릿 설명입니다.
LLM 설명을 붙이고 싶으면 `explainer(candidate, vacancy)` 콜백을 넘기면 됩니다.

```python
from features.recommendation.service import recommend_replacements

def llm_explainer(candidate, vacancy):
    return "LLM이 생성한 설명"

result = recommend_replacements(payload, top_k=5, explainer=llm_explainer)
```
