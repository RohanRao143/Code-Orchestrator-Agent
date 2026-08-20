# supervisor.py

import json
import requests
import psycopg2

from typing import Any

from state_schema import AgentOrchestratorState

from app_context import (
    get_relevant_context,
    build_supervisor_prompt,
)


# ============================================================
# CONFIG
# ============================================================

OLLAMA_API = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3.2:3b"

DATABASE_URL = (
    "dbname=agentdb "
    "user=postgres "
    "password=secret "
    "host=localhost"
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
            "num_ctx": 4096,
            "temperature": 0.2,
            "num_predict": 1024,
        },
    }

    response = requests.post(
        OLLAMA_API,
        json=payload,
        timeout=300,
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

        files = task.get(
            "files_affected",
            []
        )

        normalized_files = []

        for file in files:

            # ------------------------------------------------
            # New format:
            #
            # {
            #   "path": "db/schema.sql",
            #   "change_type": "edit"
            # }
            # ------------------------------------------------

            if isinstance(file, dict):

                normalized_files.append({
                    "path": file.get(
                        "path",
                        ""
                    ),
                    "change_type": file.get(
                        "change_type",
                        "edit"
                    ),
                })

            # ------------------------------------------------
            # Backward compatible:
            #
            # "db/schema.sql"
            # ------------------------------------------------

            else:

                normalized_files.append({
                    "path": str(file),
                    "change_type": "edit",
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

            "files_affected": normalized_files,
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

    context = get_relevant_context(
        requirement=user_requirement,
        project_id=project_id,

        max_files=15,
        max_chunks=40,
    )

    # ========================================================
    # 4. BUILD SUPERVISOR PROMPT
    # ========================================================

    prompt = build_supervisor_prompt(
        requirement=user_requirement,
        context=context,
    )

    # ========================================================
    # 5. SYSTEM PROMPT
    # ========================================================

    system_prompt = """
You are the Supervisor of a multi-agent software
development system.

You convert user requirements into a sequential
implementation plan.

You have access to repository context supplied by
the application.

Repository facts are authoritative.

Rules:

1. Do not invent existing files.
2. Existing files must use change_type "edit".
3. New files must use change_type "create".
4. Keep the number of affected files minimal.
5. Respect the detected project architecture.
6. Respect existing coding patterns.
7. Order tasks according to dependencies.
8. Assign each task to an appropriate domain.
9. Return ONLY valid JSON.
"""

    # ========================================================
    # 6. CALL OLLAMA
    # ========================================================

    response = call_local_llm(
        prompt=prompt,
        system_prompt=system_prompt,
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
            f"Ollama response:\n{response}"
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

    # Keep context available for later agents
    state["context_project_id"] = project_id

    state["relevant_context"] = context

    state["supervisor_prompt"] = prompt

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