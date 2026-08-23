# supervisor.py

import os
import json
import requests
import psycopg2

from typing import Any

from state_schema import AgentOrchestratorState

from app_context import (
    # get_relevant_context,
    get_code_graph_context,
    format_code_graph_context,
    build_supervisor_prompt,
    build_supervisor_prompt_code_graph,
    visualize_ui_graph,
)


# ============================================================
# CONFIG
# ============================================================

OLLAMA_API = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3.2:3b"
# DEFAULT_MODEL = "phi4-mini:latest"

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/multi_agent_coder"
)


# ============================================================
# LOCAL OLLAMA
# ============================================================

def call_local_llm(
    prompt: str,
    system_prompt: str = ""
) -> str:

    payload = {
        "model": DEFAULT_MODEL,

        "prompt": prompt,

        "system": system_prompt,

        "stream": False,

        "options": {
            "num_ctx": 32000,
            "temperature": 0.1,
            "num_predict": 8192,
        },
    }

    response = requests.post(
        OLLAMA_API,
        json=payload,
        timeout=9000,
    )

    response.raise_for_status()

    data = response.json()

    return data.get("response", "")


# ============================================================
# JSON PARSER
# ============================================================

def parse_llm_json(response: str) -> dict:

    response = response.strip()

    # --------------------------------------------------------
    # Remove markdown code fences
    # --------------------------------------------------------

    if response.startswith("```"):

        lines = response.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        response = "\n".join(lines)

    # --------------------------------------------------------
    # Parse JSON
    # --------------------------------------------------------

    try:

        result = json.loads(response)

        if isinstance(result, list):
            return {
                "tasks": result
            }

        return result

    except json.JSONDecodeError:

        # ----------------------------------------------------
        # Try to locate JSON object inside model response
        # ----------------------------------------------------

        start = response.find("{")
        end = response.rfind("}")

        if start != -1 and end != -1:

            candidate = response[
                start:end + 1
            ]

            try:
                return json.loads(candidate)

            except json.JSONDecodeError:
                pass

    return {
        "tasks": []
    }


# ============================================================
# NORMALIZE TASKS
# ============================================================

def normalize_task_checklist(
    result: dict
) -> list:

    tasks = result.get(
        "tasks",
        result.get(
            "task_checklist",
            []
        )
    )

    normalized = []

    for index, task in enumerate(
        tasks,
        start=1
    ):

        files_affected = task.get(
            "files_affected",
            []
        )

        files = []

        for file_info in files_affected:

            # ------------------------------------------------
            # New format:
            #
            # {
            #   "path": "db/schema.sql",
            #   "change_type": "edit"
            # }
            # ------------------------------------------------

            if isinstance(file_info, str):

                files.append({
                    "path": file_info,
                    "change_type": "edit"
                })

                continue

            if not isinstance(
                file_info,
                dict
            ):
                continue

            path = file_info.get("path")

            if not path:
                continue

            change_type = file_info.get(
                "change_type",
                "edit"
            )

            if change_type not in (
                "edit",
                "create"
            ):
                change_type = "edit"

            files.append({
                "path": path,
                "change_type": change_type
            })

        normalized.append({
            "step_id": task.get(
                "step_id",
                index
            ),

            "domain": task.get(
                "domain",
                "general"
            ),

            "description": task.get(
                "description",
                ""
            ),

            "files_affected": files,
        })

    return normalized


# ============================================================
# SAVE WORKFLOW
# ============================================================

def save_workflow(
    user_requirement: str,
    task_checklist: list
) -> int:

    conn = psycopg2.connect(
        DATABASE_URL
    )

    try:

        with conn.cursor() as cursor:

            # ------------------------------------------------
            # CREATE WORKFLOW
            # ------------------------------------------------

            cursor.execute(
                """
                INSERT INTO agent_workflows
                (
                    user_requirement,
                    current_status,
                    current_task_index
                )
                VALUES
                (
                    %s,
                    %s,
                    %s
                )
                RETURNING workflow_id
                """,
                (
                    user_requirement,
                    "ACTIVE",
                    0,
                )
            )

            workflow_id = cursor.fetchone()[0]

            # ------------------------------------------------
            # CREATE TASKS
            # ------------------------------------------------

            for task in task_checklist:

                files = task.get(
                    "files_affected",
                    []
                )

                # DB currently expects TEXT[]
                #
                # Convert:
                #
                # [
                #   {"path": "db/schema.sql"}
                # ]
                #
                # into:
                #
                # ["db/schema.sql"]

                file_paths = [
                    file["path"]
                    if isinstance(file, dict)
                    else str(file)
                    for file in files
                ]

                # Determine overall change type.
                #
                # If any file is created, mark task as create.
                # Otherwise edit.

                change_type = "edit"

                if any(
                    isinstance(file, dict)
                    and file.get("change_type") == "create"
                    for file in files
                ):
                    change_type = "create"

                cursor.execute(
                    """
                    INSERT INTO agent_tasks
                    (
                        workflow_id,
                        step_number,
                        domain,
                        task_description,
                        files_affected,
                        change_type,
                        status
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    """,
                    (
                        workflow_id,

                        task["step_id"],

                        task["domain"],

                        task["description"],

                        file_paths,

                        change_type,

                        "PENDING",
                    )
                )

        conn.commit()

        return workflow_id

    finally:
        conn.close()


# ============================================================
# SUPERVISOR
# ============================================================

def run_supervisor(
    state: AgentOrchestratorState
):

    # ========================================================
    # 1. GET USER REQUIREMENT
    # ========================================================

    user_requirement = state[
        "user_requirement"
    ]

    # ========================================================
    # 2. GET CONTEXT PROJECT
    # ========================================================
    #
    # This must have been initialized before the workflow:
    #
    # project_id = init_context(...)
    #
    # and stored in state.
    #

    project_id = state.get(
        "context_project_id"
    )

    if not project_id:

        raise ValueError(
            "context_project_id is missing from "
            "AgentOrchestratorState. "
            "Run init_context() first."
        )

    # ========================================================
    # 3. RETRIEVE RELEVANT CONTEXT
    # ========================================================

    # context = get_relevant_context(
    #     requirement=user_requirement,
    #     project_id=project_id,

    #     max_files=15,
    #     max_chunks=40,
    # )

    # UPGRADED FROM LEXICAL CHUNKING RETRIEVAL TO CODE GRAPH NETWORK

    context = get_code_graph_context(
        requirement=user_requirement,
        project_id=project_id,
        max_files=20,
        max_symbols=40,
        max_chunks=20,
        graph_depth=2,
    )

    context_text = format_code_graph_context(
        context,
        max_chars=18000,
    )

    # ========================================================
    # 3A. BUILD UI COMPONENT GRAPH
    # ========================================================

    ui_graph_text = visualize_ui_graph(
        project_id=project_id,
        max_depth=5,
        output="return",
    )


    # ========================================================
    # 4. BUILD SUPERVISOR PROMPT
    # ========================================================

    prompt = build_supervisor_prompt_code_graph(
        requirement=user_requirement,
        context=context,
        context_text=context_text,
        ui_graph_text=ui_graph_text,
    )

    # ========================================================
    # 4. BUILD SUPERVISOR PROMPT
    # ========================================================

    # prompt = build_supervisor_prompt(
    #     requirement=user_requirement,
    #     context=context,
    # )

    # ========================================================
    # 5. SYSTEM PROMPT
    # ========================================================

    SUPERVISOR_SYSTEM_PROMPT = """
You are the SUPERVISOR AGENT in a software engineering orchestration system.

You are NOT a coder.
You are NOT an architect.
You are NOT allowed to generate source code.

Your ONLY responsibility is:

1. Understand the user's software requirement.
2. Inspect the supplied repository context.
3. Decompose the requirement into a small ordered sequence of implementation tasks.
4. Identify the existing files that must be edited.
5. Identify files that must be created only when necessary.
6. Assign each task a technical domain.
7. Order tasks according to dependencies.

============================================================
STRICT OUTPUT CONTRACT
============================================================

Your response MUST be valid JSON.

Your response MUST contain EXACTLY this top-level structure:

{
  "task_checklist": [
    {
      "step_id": 1,
      "domain": "string",
      "description": "string",
      "files_affected": [
        {
          "path": "string",
          "change_type": "edit"
        }
      ]
    }
  ]
}

The following fields are REQUIRED:

task_checklist
step_id
domain
description
files_affected
path
change_type

change_type MUST be one of:

"edit"
"create"

============================================================
STRICT RULES
============================================================

DO NOT output:

- source code
- TypeScript
- JavaScript
- Python
- SQL
- Markdown
- explanations
- comments outside JSON
- ``` fences
- "Here is..."
- "I modified..."
- implementation details that belong to the Coder

DO NOT implement the requirement.

DO NOT return technical specifications.

DO NOT return generated code.

DO NOT return the complete AgentOrchestratorState.

Return ONLY the task_checklist state update.

============================================================
FILE RULES
============================================================

If a file exists in the repository context:

    change_type = "edit"

If the file does not exist and is genuinely required:

    change_type = "create"

Never invent a file when an existing file can be modified.

Prefer the smallest possible set of affected files.

Use repository paths exactly as supplied by the context.

============================================================
TASK RULES
============================================================

Each task must represent one coherent implementation step.

Tasks must be ordered by dependency.

Example:

1. database/schema
2. backend/service
3. backend/controller
4. frontend/service
5. frontend/component
6. tests

Do not combine unrelated changes into one task.

============================================================
FINAL REQUIREMENT
============================================================

Return JSON ONLY.

The first character of your response MUST be '{'.

The last character of your response MUST be '}'.
"""

    # ========================================================
    # 6. CALL OLLAMA
    # ========================================================

    response = call_local_llm(
        prompt=prompt,
        system_prompt=SUPERVISOR_SYSTEM_PROMPT,
    )

    # ========================================================
    # 7. PARSE RESPONSE
    # ========================================================

    parsed = parse_llm_json(
        response
    )

    task_checklist = normalize_task_checklist(
        parsed
    )

    # ========================================================
    # 8. VALIDATE
    # ========================================================

    if not task_checklist:

        raise RuntimeError(
            "Supervisor failed to generate "
            "a task checklist.\n\n"
            f"Ollama response:\n{response}\n"
            f"Parsed response:\n{parsed}\n"
            f"task list:\n{task_checklist}"
        )

    # ========================================================
    # 9. SAVE WORKFLOW + TASKS
    # ========================================================

    workflow_id = save_workflow(
        user_requirement=user_requirement,
        task_checklist=task_checklist,
    )

    # ========================================================
    # 10. UPDATE LANGGRAPH STATE
    # ========================================================

    state["workflow_id"] = workflow_id

    state["task_checklist"] = task_checklist

    state["current_task_index"] = 0

    # ------------------------------------------------------------
    # SELECT FIRST TASK
    # ------------------------------------------------------------

    if not task_checklist:
        raise RuntimeError(
            "Supervisor produced an empty task checklist."
        )

    first_task = task_checklist[0]

    state["current_task"] = first_task

    # ------------------------------------------------------------
    # Context
    # ------------------------------------------------------------

    state["context_project_id"] = project_id

    state["relevant_context"] = context

    state["supervisor_prompt"] = prompt

    # ------------------------------------------------------------
    # Reset execution state
    # ------------------------------------------------------------

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





# # supervisor.py
# import sys
# import json
# import psycopg2
# from typing import Dict, Any
# from state_schema import AgentOrchestratorState


# # Define local Ollama client configuration
# OLLAMA_API = "http://localhost:11434/api/generate"
# DEFAULT_MODEL = "llama3.2:3b"

# # Memory-Safe Ollama Caller
# def call_local_llm(prompt: str, system_prompt: str = "") -> str:
#     payload = {
#         "model": DEFAULT_MODEL,
#         "prompt": prompt,
#         "system": system_prompt,
#         "stream": False,
#         "options": {
#             "num_ctx": 4096,      # Guard context limit strictly
#             "temperature": 0.2,   # Lower temperature for coding stability
#             "num_predict": 1024   # Clamp predictions to avoid runaway tokens
#         }
#     }
#     response = requests.post(OLLAMA_API, json=payload)
#     return response.json().get("response", "")


# def run_supervisor(state: AgentOrchestratorState):
#     # 1. Access DB using standard context to locate matching files
#     conn = psycopg2.connect("dbname=agentdb user=postgres password=secret host=localhost")
#     cursor = conn.cursor()

#     # 2. Compile system prompt with codebase catalog metadata
#     system_prompt = (
#         "You are the Planning & Policy Unit. Decompose the user request into sequential steps. "
#         "Each step must affect minimal files. Output JSON ONLY matching the task_checklist format."
#     )
    
#     # 3. Invoke local model via Ollama (e.g., Phi-3.5-mini-instruct)
#     # response = ollama.generate(model='phi3.5:latest', prompt=...)
#     # Mock result matching the contract:
#     # task_checklist = [
#     #     {"step_id": 1, "domain": "postgres", "description": "Create 'audit_logs' table schema...", "files_affected": ["db/schema.sql"]},
#     #     {"step_id": 2, "domain": "node_express", "description": "Implement Express router...", "files_affected": ["routes/audit.js"]},
#     #     {"step_id": 3, "domain": "angular", "description": "Create Angular service...", "files_affected": ["src/app/services/audit.service.ts"]}
#     # ]
    
#      # 3. Invoke local model via Ollama (e.g., Phi-3.5-mini-instruct)
#     prompt = f"Decompose the following user requirement into sequential steps: {state['user_requirement']}"
#     response = call_local_llm(prompt, system_prompt)
    
#     # 4. Parse the response to extract the task checklist
#     try:
#         task_checklist = json.loads(response)
#     except json.JSONDecodeError:
#         task_checklist = []
    
#     # 4. Save checklist to PostgreSQL to update Global State
#     cursor.execute(
#         "INSERT INTO agent_workflows (workflow_id, user_requirement, current_status, current_task_index) "
#         "VALUES (%s, %s, 'ACTIVE', 0) ON CONFLICT (workflow_id) DO UPDATE SET current_task_index = 0;",
#         (workflow_id, user_requirement)
#     )
#     for step in task_checklist:
#         cursor.execute(
#             "INSERT INTO agent_tasks (workflow_id, step_number, domain, task_description, files_affected, status) "
#             "VALUES (%s, %s, %s, %s, %s, 'PENDING');",
#             (workflow_id, step["step_id"], step["domain"], step["description"], step["files_affected"])
#         )
#     conn.commit()
#     cursor.close()
#     conn.close()

#     state['workflow_id'] = 1
#     state['user_requirement'] = user_requirement
#     state['task_checklist'] = task_checklist
#     state['current_task_index'] = 0

    
#     return state

# # if __name__ == "__main__":
# #     # Standard CLI wrapper to receive JSON inputs from Node process
# #     input_data = json.loads(sys.stdin.read())
# #     output = run_supervisor(input_data["workflow_id"], input_data["user_requirement"])
# #     print(json.dumps(output))