# AI 근무표 생성 API - Response Body 명세

## 개요

AI 근무표 생성 API는 지정한 기간의 근무표를 생성한 뒤, 생성 결과와 공정성 지표, 경고, solver 실행 정보를 함께 반환한다.

---

## Response Body

```json
{
  "status": "SUCCESS",
  "message": "근무표 생성이 완료되었습니다.",
  "assignments": [
    {
      "date": "2026-04-30",
      "userId": 102,
      "userName": "박성훈",
      "shiftName": "Evening",
      "startTime": "15:00",
      "endTime": "23:00"
    }
  ],
  "fairnessSummary": {
    "totalsPerEmployee": [20, 20, 20, 20, 20, 20],
    "nightPerEmployee": [5, 5, 5, 5, 5, 5],
    "weekendPerEmployee": [5, 5, 6, 6, 5, 5],
    "totalSpread": 0,
    "nightSpread": 0,
    "weekendSpread": 1
  },
  "warnings": [],
  "solverMeta": {
    "status": "OPTIMAL",
    "objectiveValue": 208.0,
    "bestBound": 208.0,
    "wallTimeSeconds": 0.3229735,
    "timeLimitSeconds": 15,
    "nightEligibleEmployeeIndices": [0, 1, 2, 3, 4, 5],
    "nightEligibleCount": 6,
    "nightSpreadEligibleOnly": 0
  },
  "unassignedShifts": []
}
```

---

## 최상위 필드 명세

| 필드명                | 타입              | 필수 | 설명                 |
| ------------------ | --------------- | -: | ------------------ |
| `status`           | `string`        |  Y | 근무표 생성 결과 상태       |
| `message`          | `string`        |  Y | 결과 메시지             |
| `assignments`      | `array<object>` |  Y | 생성된 근무표 배정 목록      |
| `fairnessSummary`  | `object`        |  Y | 근무 배정 공정성 요약 지표    |
| `warnings`         | `array<string>` |  Y | 품질 관련 경고 메시지 목록    |
| `solverMeta`       | `object`        |  Y | solver 실행 및 디버그 정보 |
| `unassignedShifts` | `array<object>` |  Y | 배정되지 못한 시프트 목록     |

---

## 1. `status`

| 값         | 설명                       |
| --------- | ------------------------ |
| `SUCCESS` | 모든 하드 제약을 만족하는 근무표 생성 성공 |
| `FAILED`  | 모든 하드 제약을 만족하는 근무표 생성 실패 |

---

## 2. `message`

| 타입       | 설명                 |
| -------- | ------------------ |
| `string` | 생성 결과에 대한 사용자용 메시지 |

예시:

* `근무표 생성이 완료되었습니다.`
* `시간 제한 내에서 실행 가능한 최선안을 반환했습니다.`
* `사전 검증에서 배정 불가능한 시프트가 발견되었습니다.`

---

## 3. `assignments`

생성된 최종 근무표 목록이다.
배열의 각 원소는 1건의 배정 정보를 의미한다.

### `assignments[]` 필드 명세

| 필드명         | 타입       | 필수 | 설명                   |
| ----------- | -------- | -: | -------------------- |
| `date`      | `string` |  Y | 근무 일자 (`YYYY-MM-DD`) |
| `userId`    | `number` |  Y | 직원 ID                |
| `userName`  | `string` |  Y | 직원 이름                |
| `shiftName` | `string` |  Y | 배정된 근무 유형명           |
| `startTime` | `string` |  Y | 근무 시작 시간 (`HH:mm`)   |
| `endTime`   | `string` |  Y | 근무 종료 시간 (`HH:mm`)   |

예시:

```json
{
  "date": "2026-04-30",
  "userId": 105,
  "userName": "홍길동",
  "shiftName": "Night",
  "startTime": "23:00",
  "endTime": "07:00"
}
```

---

## 4. `fairnessSummary`

근무표의 공정성을 나타내는 요약 지표다.
발표, 관리자 리포트, 품질 검증에 활용할 수 있다.

### `fairnessSummary` 필드 명세

| 필드명                  | 타입              | 설명                        |
| -------------------- | --------------- | ------------------------- |
| `totalsPerEmployee`  | `array<number>` | 직원별 총 근무 횟수               |
| `nightPerEmployee`   | `array<number>` | 직원별 야간 근무 횟수              |
| `weekendPerEmployee` | `array<number>` | 직원별 주말 근무 횟수              |
| `totalSpread`        | `number`        | 총 근무 횟수 편차 (`최대값 - 최소값`)  |
| `nightSpread`        | `number`        | 야간 근무 횟수 편차 (`최대값 - 최소값`) |
| `weekendSpread`      | `number`        | 주말 근무 횟수 편차 (`최대값 - 최소값`) |

### 의미

* `totalsPerEmployee`

  * 각 직원이 전체 기간 동안 몇 번 근무했는지 나타냄
* `nightPerEmployee`

  * 각 직원이 야간 근무를 몇 번 맡았는지 나타냄
* `weekendPerEmployee`

  * 각 직원이 주말 근무를 몇 번 맡았는지 나타냄
* `totalSpread`

  * 총 근무 수의 최대/최소 차이
  * `0`이면 완전 균등
* `nightSpread`

  * 야간 근무 수의 최대/최소 차이
  * `0`이면 완전 균등
* `weekendSpread`

  * 주말 근무 수의 최대/최소 차이
  * 값이 작을수록 균형적

예시:

```json
"fairnessSummary": {
  "totalsPerEmployee": [20, 20, 20, 20, 20, 20],
  "nightPerEmployee": [5, 5, 5, 5, 5, 5],
  "weekendPerEmployee": [5, 5, 6, 6, 5, 5],
  "totalSpread": 0,
  "nightSpread": 0,
  "weekendSpread": 1
}
```

---

## 5. `warnings`

근무표는 생성되었지만 품질상 주의가 필요한 경우 반환되는 경고 목록이다.

| 타입              | 설명                     |
| --------------- | ---------------------- |
| `array<string>` | 공정성 또는 품질 관련 경고 메시지 목록 |

예시:

```json
["야간 근무 편차가 다소 큽니다."]
```

현재 예시:

```json
[]
```

의미:

* 경고 없음
* 공정성 품질이 양호함

---

## 6. `solverMeta`

solver 실행 정보 및 디버그용 메타데이터다.
운영/개발/성능 분석용으로 사용하며, 일반 사용자 화면에는 그대로 노출하지 않아도 된다.

### `solverMeta` 필드 명세

| 필드명                            | 타입              | 설명                       |
| ------------------------------ | --------------- | ------------------------ |
| `status`                       | `string`        | solver 상태                |
| `objectiveValue`               | `number`        | 최종 목적함수 값                |
| `bestBound`                    | `number`        | solver가 계산한 최적 경계값       |
| `wallTimeSeconds`              | `number`        | 실제 solver 실행 시간(초)       |
| `timeLimitSeconds`             | `number`        | 설정된 최대 실행 시간(초)          |
| `nightEligibleEmployeeIndices` | `array<number>` | 야간 근무 가능 직원 인덱스 목록       |
| `nightEligibleCount`           | `number`        | 야간 근무 가능 직원 수            |
| `nightSpreadEligibleOnly`      | `number`        | 야간 가능 직원만 대상으로 계산한 야간 편차 |

### 의미

* `status`

  * `OPTIMAL`: 최적해 도출
  * `FEASIBLE`: 시간 제한 내 실행 가능한 해 도출
* `objectiveValue`

  * 목적함수 점수
  * 클수록 더 좋은 해
* `bestBound`

  * 이론적 최적 경계
  * `objectiveValue == bestBound`면 최적해로 해석 가능
* `wallTimeSeconds`

  * solver가 실제로 계산에 사용한 시간
* `timeLimitSeconds`

  * solver에 설정된 최대 시간 제한
* `nightEligibleEmployeeIndices`

  * 야간 배정이 가능한 직원의 내부 인덱스 목록
* `nightEligibleCount`

  * 야간 배정 가능 인원 수
* `nightSpreadEligibleOnly`

  * 야간 가능한 직원들만 기준으로 계산한 야간 편차

예시:

```json
"solverMeta": {
  "status": "OPTIMAL",
  "objectiveValue": 208.0,
  "bestBound": 208.0,
  "wallTimeSeconds": 0.3229735,
  "timeLimitSeconds": 15,
  "nightEligibleEmployeeIndices": [0, 1, 2, 3, 4, 5],
  "nightEligibleCount": 6,
  "nightSpreadEligibleOnly": 0
}
```

---

## 7. `unassignedShifts`

모든 하드 제약을 만족하지 못해 배정되지 않은 시프트 목록이다.
성공 시 보통 빈 배열이다.

| 타입              | 설명            |
| --------------- | ------------- |
| `array<object>` | 미배정 시프트 정보 목록 |

현재 예시:

```json
[]
```

실패 예시:

```json
[
  {
    "date": "2026-04-03",
    "shiftName": "Night",
    "reasonCode": "SHIFT_CAPACITY_SHORTAGE",
    "reason": "ICU 자격을 가진 야간 가능 인원이 부족합니다."
  }
]
```

권장 필드:

| 필드명          | 타입       | 설명         |
| ------------ | -------- | ---------- |
| `date`       | `string` | 배정 실패 일자   |
| `shiftName`  | `string` | 배정 실패 시프트명 |
| `reasonCode` | `string` | 실패 사유 코드   |
| `reason`     | `string` | 실패 사유 설명   |

---

# 성공 응답 예시

```json
{
  "status": "SUCCESS",
  "message": "근무표 생성이 완료되었습니다.",
  "assignments": [
    {
      "date": "2026-04-30",
      "userId": 102,
      "userName": "박성훈",
      "shiftName": "Evening",
      "startTime": "15:00",
      "endTime": "23:00"
    },
    {
      "date": "2026-04-30",
      "userId": 103,
      "userName": "이철수",
      "shiftName": "Day",
      "startTime": "07:00",
      "endTime": "15:00"
    },
    {
      "date": "2026-04-30",
      "userId": 105,
      "userName": "홍길동",
      "shiftName": "Night",
      "startTime": "23:00",
      "endTime": "07:00"
    },
    {
      "date": "2026-04-30",
      "userId": 106,
      "userName": "정은지",
      "shiftName": "Day",
      "startTime": "07:00",
      "endTime": "15:00"
    }
  ],
  "fairnessSummary": {
    "totalsPerEmployee": [20, 20, 20, 20, 20, 20],
    "nightPerEmployee": [5, 5, 5, 5, 5, 5],
    "weekendPerEmployee": [5, 5, 6, 6, 5, 5],
    "totalSpread": 0,
    "nightSpread": 0,
    "weekendSpread": 1
  },
  "warnings": [],
  "solverMeta": {
    "status": "OPTIMAL",
    "objectiveValue": 208.0,
    "bestBound": 208.0,
    "wallTimeSeconds": 0.3229735,
    "timeLimitSeconds": 15,
    "nightEligibleEmployeeIndices": [0, 1, 2, 3, 4, 5],
    "nightEligibleCount": 6,
    "nightSpreadEligibleOnly": 0
  },
  "unassignedShifts": []
}
```

---

# 실패 응답 예시

```json
{
  "status": "FAILED",
  "message": "사전 검증에서 배정 불가능한 시프트가 발견되었습니다.",
  "assignments": [],
  "fairnessSummary": {
    "totalsPerEmployee": [],
    "nightPerEmployee": [],
    "weekendPerEmployee": [],
    "totalSpread": 0,
    "nightSpread": 0,
    "weekendSpread": 0
  },
  "warnings": [],
  "solverMeta": {
    "status": "PRECHECK_FAILED",
    "timeLimitSeconds": 15
  },
  "unassignedShifts": [
    {
      "date": "2026-04-03",
      "shiftName": "Night",
      "reasonCode": "SHIFT_CAPACITY_SHORTAGE",
      "reason": "ICU 자격을 가진 야간 가능 인원이 부족합니다."
    }
  ]
}
