import json
import os
import re
from typing import Any, Dict, List

from features.scheduling.catalog import build_constraint_catalog


def parse_user_request(user_request: str, input_json: Dict[str, Any]) -> Dict[str, Any]:
    if not user_request or not user_request.strip():
        return {
            "instructions": [],
            "warnings": [],
            "mode": "empty",
        }

    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        try:
            return _call_llm_parser(user_request, input_json)
        except Exception as exc:
            fallback = _fallback_parse(user_request, input_json)
            fallback["warnings"].append(
                {
                    "code": "LLM_PARSE_FALLBACK",
                    "message": f"LLM 파싱 실패로 fallback parser를 사용했습니다: {exc}",
                    "sourceText": user_request,
                }
            )
            return fallback

    return _fallback_parse(user_request, input_json)


def _call_llm_parser(user_request: str, input_json: Dict[str, Any]) -> Dict[str, Any]:
    from google import genai

    client = genai.Client()

    catalog = build_constraint_catalog()
    employees = [
        {
            "userId": e["userId"],
            "userName": e["userName"],
        }
        for e in input_json.get("employees", [])
    ]
    shift_names = [s["name"] for s in input_json.get("shifts", [])]

    prompt = f"""
너는 근무표 자연어 요청을 구조화된 제약으로 변환하는 파서다.

반드시 지켜라:
1. supported_constraints 안에 있는 type만 사용한다.
2. supported_constraints에 있는 요청은 가능한 한 supported=true 로 변환한다.
3. 애매하거나 정말 매핑 불가능한 요청만 supported=false 로 둔다.
4. 추측하지 마라.
5. 출력은 JSON만 반환한다.

[supported_constraints]
{json.dumps(catalog, ensure_ascii=False, indent=2)}

[employees]
{json.dumps(employees, ensure_ascii=False, indent=2)}

[shift_names]
{json.dumps(shift_names, ensure_ascii=False, indent=2)}

[important examples]

input: "김민지는 2026-04-10 쉬게 해줘"
output:
{{
  "instructions": [
    {{
      "type": "ADD_OFFDAY",
      "supported": true,
      "userId": 101,
      "date": "2026-04-10",
      "sourceText": "김민지는 2026-04-10 쉬게 해줘"
    }}
  ],
  "warnings": [],
  "mode": "llm"
}}

input: "야간은 최대한 공평하게 해줘"
output:
{{
  "instructions": [
    {{
      "type": "BOOST_NIGHT_FAIRNESS",
      "supported": true,
      "value": 8,
      "sourceText": "야간은 최대한 공평하게 해줘"
    }}
  ],
  "warnings": [],
  "mode": "llm"
}}

input: "주말은 최대한 공평하게 해줘"
output:
{{
  "instructions": [
    {{
      "type": "BOOST_WEEKEND_FAIRNESS",
      "supported": true,
      "value": 5,
      "sourceText": "주말은 최대한 공평하게 해줘"
    }}
  ],
  "warnings": [],
  "mode": "llm"
}}

input: "하루 최대 1개 시프트만 유지해줘"
output:
{{
  "instructions": [
    {{
      "type": "SET_MAX_SHIFTS_PER_DAY",
      "supported": true,
      "value": 1,
      "sourceText": "하루 최대 1개 시프트만 유지해줘"
    }}
  ],
  "warnings": [],
  "mode": "llm"
}}

input: "김민지는 2026-04-10 근무 금지"
output:
{{
  "instructions": [
    {{
      "type": "FORBID_DATE",
      "supported": true,
      "userId": 101,
      "date": "2026-04-10",
      "sourceText": "김민지는 2026-04-10 근무 금지"
    }}
  ],
  "warnings": [],
  "mode": "llm"
}}

input: "김민지 Night 금지"
output:
{{
  "instructions": [
    {{
      "type": "FORBID_SHIFT",
      "supported": true,
      "userId": 101,
      "shiftName": "Night",
      "sourceText": "김민지 Night 금지"
    }}
  ],
  "warnings": [],
  "mode": "llm"
}}

input: "분위기 좋게 짜줘"
output:
{{
  "instructions": [],
  "warnings": [
    {{
      "code": "UNSUPPORTED_REQUEST",
      "message": "지원되지 않는 요청 설명",
      "sourceText": "분위기 좋게 짜줘"
    }}
  ],
  "mode": "llm"
}}

[user_request]
{user_request}

아래 JSON 형식으로만 응답해라.
{{
  "instructions": [
    {{
      "type": "ADD_OFFDAY",
      "supported": true,
      "userId": 101,
      "date": "2026-04-10",
      "sourceText": "김민지는 2026-04-10 쉬게"
    }}
  ],
  "warnings": [
    {{
      "code": "UNSUPPORTED_REQUEST",
      "message": "지원되지 않는 요청 설명",
      "sourceText": "분위기 좋게"
    }}
  ],
  "mode": "llm"
}}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    text = getattr(response, "text", "") or ""
    parsed = _extract_json_object(text)
    if not isinstance(parsed, dict):
        raise ValueError("LLM parser did not return a valid JSON object.")

    parsed.setdefault("instructions", [])
    parsed.setdefault("warnings", [])
    parsed["mode"] = "llm"

    parsed = normalize_llm_parse_result(parsed, user_request)
    return parsed


def _fallback_parse(user_request: str, input_json: Dict[str, Any]) -> Dict[str, Any]:
    employees = input_json.get("employees", [])
    employee_name_to_id = {e["userName"]: e["userId"] for e in employees}
    shift_names = {s["name"] for s in input_json.get("shifts", [])}

    instructions: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    for name, user_id in employee_name_to_id.items():
        pattern = rf"{re.escape(name)}.*?(\d{{4}}-\d{{2}}-\d{{2}}).*?(쉬게|휴무|오프)"
        match = re.search(pattern, user_request)
        if match:
            instructions.append(
                {
                    "type": "ADD_OFFDAY",
                    "supported": True,
                    "userId": user_id,
                    "employeeName": name,
                    "date": match.group(1),
                    "sourceText": match.group(0),
                }
            )

    for name, user_id in employee_name_to_id.items():
        pattern = rf"{re.escape(name)}.*?(최대)\s*(\d+)\s*(회|번|근무)"
        match = re.search(pattern, user_request)
        if match:
            instructions.append(
                {
                    "type": "SET_MAX_ASSIGNMENTS",
                    "supported": True,
                    "userId": user_id,
                    "employeeName": name,
                    "value": int(match.group(2)),
                    "sourceText": match.group(0),
                }
            )

    for name, user_id in employee_name_to_id.items():
        pattern = rf"{re.escape(name)}.*?(연속)\s*(최대)?\s*(\d+)\s*(일)"
        match = re.search(pattern, user_request)
        if match:
            instructions.append(
                {
                    "type": "SET_MAX_CONSECUTIVE_DAYS",
                    "supported": True,
                    "userId": user_id,
                    "employeeName": name,
                    "value": int(match.group(3)),
                    "sourceText": match.group(0),
                }
            )

    match = re.search(r"(?:하루|1일).*?최대\s*(\d+)\s*(?:개|회)?\s*(?:시프트|근무)", user_request)
    if match:
        instructions.append(
            {
                "type": "SET_MAX_SHIFTS_PER_DAY",
                "supported": True,
                "value": int(match.group(1)),
                "sourceText": match.group(0),
            }
        )

    for name, user_id in employee_name_to_id.items():
        for shift_name in shift_names:
            pattern = rf"{re.escape(name)}.*?{re.escape(shift_name)}.*?(선호|우선)"
            match = re.search(pattern, user_request)
            if match:
                instructions.append(
                    {
                        "type": "PREFER_SHIFT",
                        "supported": True,
                        "userId": user_id,
                        "employeeName": name,
                        "shiftName": shift_name,
                        "sourceText": match.group(0),
                    }
                )

    if "야간" in user_request and ("공평" in user_request or "골고루" in user_request):
        instructions.append(
            {
                "type": "BOOST_NIGHT_FAIRNESS",
                "supported": True,
                "value": 8,
                "sourceText": "야간은 최대한 공평하게",
            }
        )

    if "주말" in user_request and ("공평" in user_request or "골고루" in user_request):
        instructions.append(
            {
                "type": "BOOST_WEEKEND_FAIRNESS",
                "supported": True,
                "value": 5,
                "sourceText": "주말은 최대한 공평하게",
            }
        )

    for name, user_id in employee_name_to_id.items():
        pattern = rf"{re.escape(name)}.*?(\d{{4}}-\d{{2}}-\d{{2}}).*?(근무 금지|근무 제외|일 못 하게|배정 금지)"
        match = re.search(pattern, user_request)
        if match:
            instructions.append(
                {
                    "type": "FORBID_DATE",
                    "supported": True,
                    "userId": user_id,
                    "employeeName": name,
                    "date": match.group(1),
                    "sourceText": match.group(0),
                }
            )

    for name, user_id in employee_name_to_id.items():
        for shift_name in shift_names:
            pattern = rf"{re.escape(name)}.*?{re.escape(shift_name)}.*?(금지|못|제외|빼)"
            match = re.search(pattern, user_request)
            if match:
                instructions.append(
                    {
                        "type": "FORBID_SHIFT",
                        "supported": True,
                        "userId": user_id,
                        "employeeName": name,
                        "shiftName": shift_name,
                        "sourceText": match.group(0),
                    }
                )

    unsupported_keywords = ["분위기 좋게", "인간적으로", "덜 힘들게", "잘 맞는 사람끼리"]
    for keyword in unsupported_keywords:
        if keyword in user_request:
            warnings.append(
                {
                    "code": "UNSUPPORTED_REQUEST",
                    "message": f"'{keyword}' 요청은 현재 규칙으로 직접 매핑할 수 없어 적용되지 않았습니다.",
                    "sourceText": keyword,
                }
            )

    return {
        "instructions": instructions,
        "warnings": warnings,
        "mode": "fallback",
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


def normalize_llm_parse_result(parse_result: Dict[str, Any], user_request: str) -> Dict[str, Any]:
    instructions = list(parse_result.get("instructions", []))
    warnings = list(parse_result.get("warnings", []))

    def _has_supported(inst_type: str) -> bool:
        return any(
            inst.get("type") == inst_type and inst.get("supported") is True
            for inst in instructions
        )

    if "야간" in user_request and ("공평" in user_request or "골고루" in user_request):
        if not _has_supported("BOOST_NIGHT_FAIRNESS"):
            instructions = [
                inst
                for inst in instructions
                if not (
                    inst.get("type") == "BOOST_NIGHT_FAIRNESS"
                    and inst.get("supported") is False
                )
            ]
            instructions.append(
                {
                    "type": "BOOST_NIGHT_FAIRNESS",
                    "supported": True,
                    "value": 8,
                    "sourceText": "야간은 최대한 공평하게 해줘",
                }
            )

    if "주말" in user_request and ("공평" in user_request or "골고루" in user_request):
        if not _has_supported("BOOST_WEEKEND_FAIRNESS"):
            instructions = [
                inst
                for inst in instructions
                if not (
                    inst.get("type") == "BOOST_WEEKEND_FAIRNESS"
                    and inst.get("supported") is False
                )
            ]
            instructions.append(
                {
                    "type": "BOOST_WEEKEND_FAIRNESS",
                    "supported": True,
                    "value": 5,
                    "sourceText": "주말은 최대한 공평하게 해줘",
                }
            )

    match = re.search(r"(?:하루|1일).*?최대\s*(\d+)\s*(?:개|회)?\s*(?:시프트|근무)", user_request)
    if match:
        value = int(match.group(1))
        if 1 <= value <= 3 and not _has_supported("SET_MAX_SHIFTS_PER_DAY"):
            instructions = [
                inst
                for inst in instructions
                if inst.get("type") != "SET_MAX_SHIFTS_PER_DAY"
            ]
            instructions.append(
                {
                    "type": "SET_MAX_SHIFTS_PER_DAY",
                    "supported": True,
                    "value": value,
                    "sourceText": match.group(0),
                }
            )

    for inst in list(instructions):
        if inst.get("type") == "FORBID_DATE" and inst.get("supported") is False:
            instructions.remove(inst)

    for inst in list(instructions):
        if inst.get("type") == "FORBID_SHIFT" and inst.get("supported") is False:
            instructions.remove(inst)

    unsupported_keywords = ["분위기 좋게 짜줘", "분위기 좋게", "인간적으로", "덜 힘들게", "잘 맞는 사람끼리"]
    for keyword in unsupported_keywords:
        if keyword in user_request:
            exists = any(w.get("sourceText") == keyword for w in warnings)
            if not exists:
                warnings.append(
                    {
                        "code": "UNSUPPORTED_REQUEST",
                        "message": "지원되지 않는 요청 설명",
                        "sourceText": keyword,
                    }
                )

    # 중복 warning 제거
    deduped_warnings = []
    seen = set()

    for w in warnings:
        source = (w.get("sourceText") or "").strip()

        # "분위기 좋게 짜줘"가 있으면 "분위기 좋게"는 버림
        if source == "분위기 좋게":
            has_longer = any(
                (other.get("sourceText") or "").strip() == "분위기 좋게 짜줘"
                for other in warnings
            )
            if has_longer:
                continue

        key = (w.get("code"), source)
        if key not in seen:
            seen.add(key)
            deduped_warnings.append(w)

    parse_result["instructions"] = instructions
    parse_result["warnings"] = deduped_warnings
    parse_result["mode"] = parse_result.get("mode", "llm")
    return parse_result