import json
import os
from typing import Any, Dict, List, Optional


REASON_TEXT = {
    "ROLE_MATCH": "역할 요건을 충족하고",
    "SKILL_MATCH": "필요 스킬을 보유했으며",
    "PREFERRED_SHIFT": "선호 근무와 일치하고",
    "REST_OK": "최소 휴식시간을 만족하고",
    "LOW_NIGHT_BIAS": "현재 야간 편중이 낮고",
    "LOW_WEEKEND_BIAS": "주말 편중이 비교적 낮고",
    "LOW_TOTAL_LOAD": "전체 배정 부담이 비교적 낮고",
    "FAIRNESS_FRIENDLY": "연속 근무 부담도 과하지 않습니다",
}


def build_recommendation_reason_text(
    employee: Dict[str, Any],
    absence: Dict[str, Any],
    reason_codes: List[str],
    score: int,
    user_request: Optional[str] = None,
    stats: Optional[Dict[str, Any]] = None,
) -> str:
    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        try:
            return _call_llm_reasoner(
                employee=employee,
                absence=absence,
                reason_codes=reason_codes,
                score=score,
                user_request=user_request or "",
                stats=stats or {},
            )
        except Exception:
            pass

    return _build_template_reason(reason_codes, stats)


def _call_llm_reasoner(
    employee: Dict[str, Any],
    absence: Dict[str, Any],
    reason_codes: List[str],
    score: int,
    user_request: str,
    stats: Dict[str, Any],
) -> str:
    from google import genai

    client = genai.Client()

    payload = {
        "candidate": {
            "userId": employee.get("userId"),
            "userName": employee.get("userName"),
            "roles": employee.get("roles", []),
            "skills": employee.get("skills", []),
            "preferredShifts": employee.get("preferredShifts", []),
        },
        "absence": absence,
        "reason_codes": reason_codes,
        "score": score,
        "user_request": user_request,
        "stats": stats,
    }

    prompt = f"""
너는 대체인력 추천 설명 생성기다.
주어진 정보만 사용해서 추천 사유를 한국어 한 문장으로 만들어라.

중요:
- 모든 후보에게 똑같이 해당되는 일반론을 나열하지 마라.
- 이 후보가 다른 후보 대비 상대적으로 강한 점 1~2개만 강조해라.
- score를 반복해서 말하지 마라.
- 40자~80자 정도로 짧고 설득력 있게 써라.
- 출력은 JSON만 허용한다.

형식:
{{
  "reasons": "추천 사유 한 문장"
}}

payload:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    text = getattr(response, "text", "") or ""
    parsed = _extract_json_object(text)
    reason_text = parsed.get("reasons", "").strip()
    if not reason_text:
        raise ValueError("Empty reasons from LLM.")
    return reason_text


def _build_template_reason(reason_codes: List[str], stats: Optional[Dict[str, Any]] = None) -> str:
    if stats is None:
        stats = {}

    if "LOW_TOTAL_LOAD" in reason_codes:
        return "현재 전체 근무 부담이 가장 낮은 편이라 대체 투입에 유리합니다."

    if "LOW_WEEKEND_BIAS" in reason_codes:
        return "주말 근무 편중이 낮아 공정성 측면에서 적합한 후보입니다."

    if "LOW_NIGHT_BIAS" in reason_codes:
        return "야간 근무 부담이 낮아 추가 배정에 상대적으로 유리합니다."

    if "PREFERRED_SHIFT" in reason_codes:
        return "해당 근무가 선호 시프트와 일치해 적응 측면에서 유리합니다."

    if "FAIRNESS_FRIENDLY" in reason_codes:
        return "연속 근무 부담이 낮아 안정적으로 투입할 수 있습니다."

    return "결원 슬롯의 기본 요건을 충족해 대체 인력으로 적합합니다."


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json", "", 1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in LLM response.")

    return json.loads(text[start:end + 1])