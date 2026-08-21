# import os
# import requests
# from typing import Dict, List, TypedDict
# from langgraph.graph import StateGraph, END

# from state_schema import AgentOrchestratorState
# from supervisor import run_supervisor
# from architect import run_architect
# from coder import run_coder
# from reviewer import run_reviewer, route_after_review


# # Compile State Graph
# workflow = StateGraph(AgentOrchestratorState)
# workflow.add_node("supervisor", run_supervisor)
# workflow.add_node("architect", run_architect)
# workflow.add_node("coder", run_coder)
# workflow.add_node("reviewer", run_reviewer)

# workflow.set_entry_point("supervisor")
# workflow.add_conditional_edges("reviewer", route_after_review, {"save_and_flush": END, "coder": "coder"})
# # (Define other transitions...)
# app = workflow.compile()



# orchestrator.py

from langgraph.graph import StateGraph, END

from state_schema import AgentOrchestratorState

from supervisor import run_supervisor
from architect import run_architect
from coder import run_coder
from reviewer import (
    run_reviewer,
    route_after_review,
)


# ============================================================
# BUILD GRAPH
# ============================================================

workflow = StateGraph(AgentOrchestratorState)


# ============================================================
# NODES
# ============================================================
workflow.add_node("supervisor", run_supervisor)
# workflow.add_node("architect", run_architect)
# workflow.add_node("coder", run_coder)
# workflow.add_node("reviewer", run_reviewer)


# ============================================================
# ENTRY
# ============================================================
workflow.set_entry_point("supervisor")

# # ============================================================
# # SUPERVISOR → ARCHITECT
# # ============================================================
# workflow.add_edge("supervisor", "architect")

# # ============================================================
# # ARCHITECT → CODER
# # ============================================================
# workflow.add_edge("architect", "coder")

# # ============================================================
# # CODER → REVIEWER
# # ============================================================
# workflow.add_edge("coder", "reviewer")

# # ============================================================
# # REVIEWER ROUTING
# # ============================================================

# workflow.add_conditional_edges("reviewer", route_after_review, { "save_and_flush": END, "coder": "coder" })

# ============================================================
# COMPILE
# ============================================================

app = workflow.compile()