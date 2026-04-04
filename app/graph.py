import os
import sys
from typing import Any, Dict, List, Optional, TypedDict

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from features.scheduling.nodes import (
    llm_parse_node,
    extract_params_node,
    solve_node,
    format_node,
    explain_node,
)


class AgentState(TypedDict):
    input_json: Dict[str, Any]
    user_request: Optional[str]

    constraint_catalog: Dict[str, Any]
    llm_parse_result: Dict[str, Any]
    parser_warnings: List[Dict[str, Any]]
    applied_instructions: List[Dict[str, Any]]
    ignored_instructions: List[Dict[str, Any]]

    solver_params: Dict[str, Any]
    raw_schedule: Dict[str, Any]
    final_schedule: Dict[str, Any]
    error_msg: Optional[str]


workflow = StateGraph(AgentState)

workflow.add_node("llm_parse", llm_parse_node)
workflow.add_node("extract", extract_params_node)
workflow.add_node("solve", solve_node)
workflow.add_node("format", format_node)
workflow.add_node("explain", explain_node)

workflow.set_entry_point("llm_parse")
workflow.add_edge("llm_parse", "extract")
workflow.add_edge("extract", "solve")


def route_after_solve(state: AgentState):
    return "end" if state.get("error_msg") else "format"


workflow.add_conditional_edges(
    "solve",
    route_after_solve,
    {
        "format": "format",
        "end": END,
    },
)

workflow.add_edge("format", "explain")
workflow.add_edge("explain", END)

graph_app = workflow.compile()