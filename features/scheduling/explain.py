import json
import os
from typing import Any, Dict, List


def generate_explanation(
    raw_result: Dict[str, Any],
    input_json: Dict[str, Any],
    applied_instructions: List[Dict[str, Any]],
    ignored_instructions: List[Dict[str, Any]],
    parser_warnings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        try:
            return _call_llm_explanation(
                raw_result=raw_result,
                input_json=input_json,
                applied_instructions=applied_instructions,
                ignored_instructions=ignored_instructions,
                parser_warnings=parser_warnings,
            )
        except Exception as exc:
            fallback = build_template_explanation(
                raw_result=raw_result,
                input_json=input_json,
                applied_instructions=applied_instructions,
                ignored_instructions=ignored_instructions,
                parser_warnings=parser_warnings,
            )
            fallback["warnings"] = [f"LLM explanation fallback 사용: {exc}"]
            return fallback

    return build_template_explanation(
        raw_result=raw_result,
        input_json=input_json,
        applied_instructions=applied_instructions,
        ignored_instructions=ignored_instructions,
        parser_warnings=parser_warnings,
    )


def _call_llm_explanation(
    raw_result: Dict[str, Any],
    input_json: Dict[str, Any],
    applied_instructions: List[Dict[str, Any]],
    ignored_instructions: List[Dict[str, Any]],
    parser_warnings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    from google import genai

    client = genai.Client()

    payload = {
        "raw_result": {
            "status": raw_result.get("status"),
            "message": raw_result.get("message"),
            "fairness_summary": raw_result.get("fairness_summary", {}),
            "warnings": raw_result.get("warnings", []),
            "solver_meta": raw_result.get("solver_meta", {}),
            "unassigned_shifts": raw_result.get("unassigned_shifts", []),
        },
        "applied_instructions": applied_instructions,
        "ignored_instructions": ignored_instructions,
        "parser_warnings": parser_warnings,
    }

    prompt = f"""
    너는 근무표 설명 시스템이다.
    아래 계산 결과만 사용해서 한국어 설명 JSON을 생성해라.
    추측하지 마라.
    설명에는 반드시 다음을 반영해라:
    - 하드 제약 충족 여부
    - 공정성 요약
    - 적용된 자연어 요청
    - 무시된 자연어 요청 또는 parser warning
    출력은 아래 JSON 형식만 허용한다.
    {{
      "mode": "llm",
      "summary": "문장 2~4개",
      "details": ["항목1", "항목2", "항목3"]
    }}

    [payload]
    {json.dumps(payload, ensure_ascii=False, indent=2)}
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    text = getattr(response, "text", "") or ""
    parsed = _extract_json_object(text)
    parsed["mode"] = "llm"
    return parsed


def build_template_explanation(
    raw_result: Dict[str, Any],
    input_json: Dict[str, Any],
    applied_instructions: List[Dict[str, Any]],
    ignored_instructions: List[Dict[str, Any]],
    parser_warnings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    fairness = raw_result.get("fairness_summary", {})
    solver_meta = raw_result.get("solver_meta", {})
    warnings = raw_result.get("warnings", [])

    summary_parts = []
    if raw_result.get("status") == "SUCCESS":
        summary_parts.append("하드 제약을 만족하는 근무표를 기준으로 생성했습니다.")
        summary_parts.append("직원별 총 근무 수 편차와 주말·야간 편중을 줄이는 방향으로 조정했습니다.")
        if applied_instructions:
            summary_parts.append(f"자연어 요청 중 {len(applied_instructions)}건을 반영했습니다.")
        if ignored_instructions or parser_warnings:
            summary_parts.append("다만 일부 자연어 요청은 현재 지원 범위를 벗어나 반영되지 않았습니다.")
    else:
        summary_parts.append("주어진 제약조건으로는 모든 시프트를 만족하는 배정을 찾지 못했습니다.")

    details = [
        "offDays, availableShifts, requiredRoles, requiredSkills를 기준으로 배정 가능 여부를 먼저 제한했습니다.",
        "최소 휴식시간과 최대 연속근무일, 하루 최대 시프트 수를 넘지 않도록 배정했습니다.",
    ]

    if fairness:
        details.append(
            f"총 근무 편차={fairness.get('totalSpread', 0)}, "
            f"야간 편차={fairness.get('nightSpread', 0)}, "
            f"주말 편차={fairness.get('weekendSpread', 0)} 기준으로 균형을 확인했습니다."
        )

    if solver_meta.get("nightEligibleCount", 0) >= 2:
        details.append("야간 가능 인원끼리 야간 근무가 과도하게 몰리지 않도록 조정했습니다.")

    details.extend([item["message"] for item in applied_instructions[:5]])
    details.extend([w["message"] for w in parser_warnings[:3]])
    details.extend([f"미반영 요청: {item.get('reason', '지원하지 않는 요청')}" for item in ignored_instructions[:3]])
    details.extend(warnings[:3])

    return {
        "mode": "template",
        "summary": " ".join(summary_parts),
        "details": details,
    }


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()
    if not text:
        raise ValueError("Empty LLM response.")
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json", "", 1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in LLM response.")
    return json.loads(text[start:end + 1])
