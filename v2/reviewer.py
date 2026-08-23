# reviewer.py

import os
import subprocess
import tempfile
from typing import Dict, Any, List

from state_schema import AgentOrchestratorState


# ============================================================
# CONFIG
# ============================================================

MAX_RETRIES = 3


# ============================================================
# RUN COMMAND
# ============================================================

def run_command(
    command: List[str],
    cwd: str = None
):

    try:

        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120
        )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }

    except subprocess.TimeoutExpired:

        return {
            "returncode": -1,
            "stdout": "",
            "stderr": "Command timed out."
        }

    except FileNotFoundError as exc:

        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc)
        }


# ============================================================
# VALIDATE JAVASCRIPT
# ============================================================

def validate_javascript(
    path: str,
    content: str
):

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".js",
        delete=False,
        encoding="utf-8"
    ) as f:

        f.write(content)

        temp_path = f.name

    try:

        return run_command(
            [
                "node",
                "--check",
                temp_path
            ]
        )

    finally:

        try:
            os.remove(temp_path)
        except OSError:
            pass


# ============================================================
# VALIDATE TYPESCRIPT
# ============================================================

def validate_typescript(
    path: str,
    content: str
):

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".ts",
        delete=False,
        encoding="utf-8"
    ) as f:

        f.write(content)

        temp_path = f.name

    try:

        return run_command(
            [
                "npx",
                "tsc",
                "--noEmit",
                temp_path
            ]
        )

    finally:

        try:
            os.remove(temp_path)
        except OSError:
            pass


# ============================================================
# VALIDATE PYTHON
# ============================================================

def validate_python(
    path: str,
    content: str
):

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        delete=False,
        encoding="utf-8"
    ) as f:

        f.write(content)

        temp_path = f.name

    try:

        return run_command(
            [
                "python",
                "-m",
                "py_compile",
                temp_path
            ]
        )

    finally:

        try:
            os.remove(temp_path)
        except OSError:
            pass


# ============================================================
# VALIDATE FILE
# ============================================================

def validate_file(
    path: str,
    content: str
):

    lower = path.lower()

    if lower.endswith(".js"):
        return validate_javascript(
            path,
            content
        )

    if lower.endswith(".ts"):
        return validate_typescript(
            path,
            content
        )

    if lower.endswith(".py"):
        return validate_python(
            path,
            content
        )

    # No compiler available.
    return {
        "returncode": 0,
        "stdout": "",
        "stderr": ""
    }


# ============================================================
# REVIEWER
# ============================================================

def run_reviewer(
    state: AgentOrchestratorState
):

    generated_files = state.get(
        "generated_files",
        {}
    )

    if not generated_files:

        # Backwards compatibility
        # for single-file execution.

        target = state.get(
            "active_target_file"
        )

        code = state.get(
            "generated_code"
        )

        if target and code is not None:

            generated_files = {
                target: code
            }

        else:

            raise ValueError(
                "Reviewer received no generated code."
            )

    errors = []

    validations = []

    # --------------------------------------------------------
    # Validate every generated file
    # --------------------------------------------------------

    for path, content in generated_files.items():

        result = validate_file(
            path,
            content
        )

        validation = {
            "file": path,
            "returncode": result["returncode"],
            "stdout": result["stdout"],
            "stderr": result["stderr"]
        }

        validations.append(
            validation
        )

        if result["returncode"] != 0:

            error = (
                f"Validation failed for {path}\n\n"
                f"{result['stderr'] or result['stdout']}"
            )

            errors.append(error)

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    if errors:

        state["compilation_status"] = (
            "failure"
        )

        state["reviewer_feedback"] = (
            "\n\n".join(errors)
        )

        state["review_result"] = {
            "status": "failure",
            "validations": validations,
            "errors": errors
        }

        return state

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    state["compilation_status"] = (
        "success"
    )

    state["reviewer_feedback"] = None

    state["review_result"] = {
        "status": "success",
        "validations": validations,
        "errors": []
    }

    # --------------------------------------------------------
    # Only write validated files
    # --------------------------------------------------------

    for path, content in generated_files.items():

        directory = os.path.dirname(path)

        if directory:

            os.makedirs(
                directory,
                exist_ok=True
            )

        with open(
            path,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(content)

    return state


# ============================================================
# ROUTING
# ============================================================

def route_after_review(
    state: AgentOrchestratorState
) -> str:

    status = state.get(
        "compilation_status",
        "failure"
    )

    retry_count = state.get(
        "retry_count",
        0
    )

    max_retries = state.get(
        "max_retries",
        MAX_RETRIES
    )

    # --------------------------------------------------------
    # Successful task
    # --------------------------------------------------------

    if status == "success":

        return "next_task"

    # --------------------------------------------------------
    # Retry exhausted
    # --------------------------------------------------------

    if retry_count >= max_retries:

        return "save_and_flush"

    # --------------------------------------------------------
    # Repair
    # --------------------------------------------------------

    return "coder"


def advance_to_next_task(
    state: AgentOrchestratorState
):
    """
    Move the orchestrator from the completed task
    to the next Supervisor-generated task.

    This node does NOT call an LLM.
    It only changes orchestration state.
    """

    task_checklist = state.get(
        "task_checklist",
        []
    )

    current_index = state.get(
        "current_task_index",
        0
    )

    next_index = current_index + 1

    # ============================================================
    # NO MORE TASKS
    # ============================================================

    if next_index >= len(task_checklist):

        state["current_task_index"] = next_index

        state["current_task"] = {}

        return state

    # ============================================================
    # SELECT NEXT TASK
    # ============================================================

    next_task = task_checklist[next_index]

    state["current_task_index"] = next_index

    state["current_task"] = next_task

    # ============================================================
    # RESET TASK-SPECIFIC STATE
    # ============================================================

    state["target_files"] = []

    state["sliced_code_context"] = ""

    state["technical_spec"] = ""

    state["generated_files"] = {}

    state["active_target_file"] = ""

    state["generated_code"] = ""

    state["compilation_status"] = "pending"

    state["reviewer_feedback"] = None

    state["review_result"] = {}

    state["retry_count"] = 0

    return state

def route_after_task_advance(
    state: AgentOrchestratorState
) -> str:

    task_checklist = state.get(
        "task_checklist",
        []
    )

    current_index = state.get(
        "current_task_index",
        0
    )

    if current_index >= len(task_checklist):
        return "save_and_flush"

    return "architect"