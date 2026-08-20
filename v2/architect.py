# architect.py

import json
import os
import re
import requests
import psycopg2
from typing import Dict, Any, List

from state_schema import AgentOrchestratorState


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

MAX_CONTEXT_CHARS = 12000
MAX_FILE_CHARS = 6000


# ============================================================
# OLLAMA
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
            "temperature": 0.1,
            "num_predict": 1200
        }
    }

    response = requests.post(
        OLLAMA_API,
        json=payload,
        timeout=300
    )

    response.raise_for_status()

    data = response.json()

    return data.get("response", "").strip()


# ============================================================
# FILE SLICING
# ============================================================

def slice_file_structure(
    raw_code: str,
    file_path: str,
    max_chars: int = MAX_FILE_CHARS
) -> str:

    if not raw_code:
        return ""

    lines = raw_code.splitlines()

    # Small file -> keep everything
    if len(raw_code) <= max_chars:
        return raw_code

    extension = os.path.splitext(file_path)[1].lower()

    important_lines = []

    # --------------------------------------------------------
    # Imports
    # --------------------------------------------------------

    for line in lines:

        stripped = line.strip()

        if (
            stripped.startswith("import ")
            or stripped.startswith("from ")
            or stripped.startswith("require(")
            or "require(" in stripped
        ):
            important_lines.append(line)

    # --------------------------------------------------------
    # Structural declarations
    # --------------------------------------------------------

    keywords = (
        "class ",
        "interface ",
        "type ",
        "enum ",
        "function ",
        "def ",
        "async def ",
        "export function ",
        "export class ",
        "export const ",
        "router.",
        "app.",
    )

    for index, line in enumerate(lines):

        stripped = line.strip()

        if any(keyword in stripped for keyword in keywords):

            start = max(0, index - 2)
            end = min(len(lines), index + 20)

            important_lines.extend(
                lines[start:end]
            )

    # --------------------------------------------------------
    # Remove duplicates while preserving order
    # --------------------------------------------------------

    seen = set()
    result = []

    for line in important_lines:

        if line not in seen:

            seen.add(line)
            result.append(line)

    sliced = "\n".join(result)

    if len(sliced) > max_chars:
        sliced = sliced[:max_chars]

    return sliced


# ============================================================
# READ FILE
# ============================================================

def read_target_file(file_path: str) -> str:

    if not os.path.exists(file_path):

        return (
            f"// FILE: {file_path}\n"
            "// STATUS: FILE DOES NOT EXIST\n"
            "// ACTION: CREATE\n"
        )

    if os.path.getsize(file_path) > 200_000:

        with open(
            file_path,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as f:

            raw_code = f.read()

        return slice_file_structure(
            raw_code,
            file_path
        )

    with open(
        file_path,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:

        raw_code = f.read()

    return slice_file_structure(
        raw_code,
        file_path
    )


# ============================================================
# BUILD CONTEXT
# ============================================================

def build_architect_context(
    state: AgentOrchestratorState
) -> str:

    current_task = state["current_task"]

    files = current_task.get(
        "files_affected",
        []
    )

    sections = []

    for file_info in files:

        if isinstance(file_info, dict):

            file_path = file_info.get(
                "path",
                ""
            )

            change_type = file_info.get(
                "change_type",
                "edit"
            )

        else:

            file_path = str(file_info)
            change_type = "edit"

        if not file_path:
            continue

        code = read_target_file(file_path)

        sections.append(
            f"""
============================================================
FILE
============================================================

Path: {file_path}
Change: {change_type}

{code}
"""
        )

    # Add repository retrieval context if available

    relevant_context = state.get(
        "relevant_context"
    )

    if relevant_context:

        chunks = relevant_context.get(
            "relevant_chunks",
            []
        )

        for chunk in chunks[:10]:

            sections.append(
                f"""
============================================================
RELATED CONTEXT
============================================================

File: {chunk.get("file")}
Lines: {chunk.get("start_line")}-{chunk.get("end_line")}

{chunk.get("content", "")}
"""
            )

    context = "\n".join(sections)

    if len(context) > MAX_CONTEXT_CHARS:

        context = context[
            :MAX_CONTEXT_CHARS
        ]

    return context


# ============================================================
# EXTRACT JSON
# ============================================================

def extract_json(text: str) -> Dict[str, Any]:

    text = text.strip()

    text = re.sub(
        r"^```json\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"^```\s*",
        "",
        text
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    try:
        return json.loads(text)

    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:

        return json.loads(
            text[start:end + 1]
        )

    raise ValueError(
        "Architect returned invalid JSON."
    )


# ============================================================
# SAVE SPEC
# ============================================================

def save_technical_spec(
    workflow_id: int,
    task_id: int,
    technical_spec: str
):

    conn = psycopg2.connect(
        DATABASE_URL
    )

    try:

        with conn.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO agent_specs (
                    workflow_id,
                    task_id,
                    technical_spec
                )
                VALUES (%s, %s, %s)
                """,
                (
                    workflow_id,
                    task_id,
                    technical_spec
                )
            )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# ARCHITECT
# ============================================================

def run_architect(
    state: AgentOrchestratorState
):

    workflow_id = state["workflow_id"]

    current_task = state.get(
        "current_task"
    )

    if not current_task:

        raise ValueError(
            "Architect received no current_task."
        )

    task_id = current_task.get(
        "task_id",
        current_task.get("step_id")
    )

    if not task_id:

        task_id = state["current_task_index"] + 1

    target_files = []

    for file_info in current_task.get(
        "files_affected",
        []
    ):

        if isinstance(file_info, dict):

            target_files.append(
                file_info["path"]
            )

        else:

            target_files.append(
                str(file_info)
            )

    context = build_architect_context(
        state
    )

    system_prompt = """
You are the Architecture Agent in a local
software engineering agent system.

Your job is to transform ONE implementation task
into a precise technical implementation specification.

Rules:

1. Do not invent existing architecture.
2. Respect the provided repository context.
3. Minimize changed files.
4. Clearly distinguish CREATE and EDIT.
5. Preserve existing interfaces unless the task requires changes.
6. Identify dependencies between affected files.
7. Specify functions/classes/routes/schema changes.
8. Specify validation requirements.
9. Do not generate implementation code.
10. Output JSON only.

Return:

{
  "summary": "...",
  "changes": [
    {
      "file": "...",
      "change_type": "create|edit",
      "changes": ["..."]
    }
  ],
  "interfaces": ["..."],
  "dependencies": ["..."],
  "validation": ["..."]
}
"""

    prompt = f"""
USER REQUIREMENT:

{state["user_requirement"]}


CURRENT TASK:

Step: {current_task.get("step_id")}
Domain: {current_task.get("domain")}

Description:

{current_task.get("description")}


TARGET FILES:

{json.dumps(target_files, indent=2)}


REPOSITORY CONTEXT:

{context}
"""

    response = call_local_llm(
        prompt,
        system_prompt
    )

    try:

        spec_json = extract_json(
            response
        )

        technical_spec = json.dumps(
            spec_json,
            indent=2
        )

    except Exception:

        # Preserve useful output even if
        # model formatting failed.

        technical_spec = response

    save_technical_spec(
        workflow_id,
        int(task_id),
        technical_spec
    )

    state["target_files"] = target_files

    state["sliced_code_context"] = context

    state["technical_spec"] = technical_spec

    return state