from typing import TypedDict, List, Dict, Optional, Any


class AgentOrchestratorState(TypedDict, total=False):

    # ============================================================
    # USER / WORKFLOW
    # ============================================================

    workflow_id: int
    user_requirement: str

    # ============================================================
    # PROJECT CONTEXT
    # ============================================================

    context_project_id: int

    relevant_context: Dict[str, Any]

    # ============================================================
    # SUPERVISOR
    # ============================================================

    task_checklist: List[Dict[str, Any]]

    current_task_index: int

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

    active_target_file: str

    generated_code: str

    generated_files: Dict[str, str]

    # ============================================================
    # REVIEWER
    # ============================================================

    compilation_status: str

    reviewer_feedback: Optional[str]

    review_result: Dict[str, Any]

    # ============================================================
    # RETRY
    # ============================================================

    retry_count: int

    max_retries: int

    # ============================================================
    # INTERNAL
    # ============================================================

    error: Optional[str]