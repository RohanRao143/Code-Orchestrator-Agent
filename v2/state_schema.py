# state_schema.py

from typing import TypedDict, List, Dict, Optional, Any


class AgentOrchestratorState(TypedDict, total=False):

    # ============================================================
    # WORKFLOW
    # ============================================================

    workflow_id: int
    user_requirement: str

    # ============================================================
    # CONTEXT
    # ============================================================

    context_project_id: int

    relevant_context: Dict[str, Any]

    code_graph_context: Dict[str, Any]

    code_graph_context_text: str

    supervisor_prompt: str

    # ============================================================
    # PLANNING
    # ============================================================

    task_checklist: List[Dict[str, Any]]

    current_task_index: int

    # IMPORTANT:
    # This is ONE task, not the entire checklist.
    current_task: Dict[str, Any]

    # ============================================================
    # ARCHITECT
    # ============================================================

    target_files: List[str]

    sliced_code_context: str

    technical_spec: str

    # ============================================================
    # CODER
    # ============================================================

    generated_files: Dict[str, str]

    active_target_file: str

    generated_code: str

    # ============================================================
    # REVIEWER
    # ============================================================

    compilation_status: str

    reviewer_feedback: Optional[str]

    review_result: Dict[str, Any]

    # ============================================================
    # RETRIES
    # ============================================================

    retry_count: int

    max_retries: int

    # ============================================================
    # INTERNAL
    # ============================================================

    error: Optional[str]