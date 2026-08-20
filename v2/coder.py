# coder.py

import json
import re
import requests
from typing import Dict, Any

from state_schema import AgentOrchestratorState


# ============================================================
# CONFIG
# ============================================================

OLLAMA_API = "http://localhost:11434/api/generate"

DEFAULT_MODEL = "qwen2.5-coder:3b"

MAX_CONTEXT_CHARS = 14000


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
            "num_predict": 2048
        }
    }

    response = requests.post(
        OLLAMA_API,
        json=payload,
        timeout=300
    )

    response.raise_for_status()

    return response.json().get(
        "response",
        ""
    ).strip()


# ============================================================
# JSON EXTRACTION
# ============================================================

def extract_json(
    text: str
) -> Dict[str, Any]:

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

        start = text.find("{")
        end = text.rfind("}")

        if start >= 0 and end > start:

            return json.loads(
                text[start:end + 1]
            )

        raise


# ============================================================
# CODER
# ============================================================

def run_coder(
    state: AgentOrchestratorState
):

    current_task = state["current_task"]

    technical_spec = state.get(
        "technical_spec",
        ""
    )

    sliced_context = state.get(
        "sliced_code_context",
        ""
    )

    reviewer_feedback = state.get(
        "reviewer_feedback"
    )

    target_files = state.get(
        "target_files",
        []
    )

    if len(sliced_context) > MAX_CONTEXT_CHARS:

        sliced_context = sliced_context[
            :MAX_CONTEXT_CHARS
        ]

    # --------------------------------------------------------
    # Retry feedback
    # --------------------------------------------------------

    retry_section = ""

    if reviewer_feedback:

        retry_section = f"""
============================================================
PREVIOUS REVIEW FAILURE
============================================================

{reviewer_feedback}

Fix the failure instead of repeating the previous mistake.
"""

    system_prompt = """
You are the Coding Agent.

You modify an existing software repository.

Rules:

1. Follow the technical specification exactly.
2. Preserve existing architecture.
3. Do not invent APIs that are not present in context.
4. Do not rewrite unrelated code.
5. Make the smallest valid change.
6. Existing files must be edited, not recreated from scratch.
7. New files may be created.
8. Preserve formatting and conventions.
9. Produce complete file contents.
10. Output JSON only.

Format:

{
  "files": [
    {
      "path": "path/to/file",
      "content": "complete file content"
    }
  ]
}
"""

    prompt = f"""
============================================================
USER REQUIREMENT
============================================================

{state["user_requirement"]}


============================================================
CURRENT TASK
============================================================

{json.dumps(current_task, indent=2)}


============================================================
TECHNICAL SPECIFICATION
============================================================

{technical_spec}


============================================================
REPOSITORY CONTEXT
============================================================

{sliced_context}

{retry_section}


============================================================
TARGET FILES
============================================================

{json.dumps(target_files, indent=2)}
"""

    response = call_local_llm(
        prompt,
        system_prompt
    )

    result = extract_json(
        response
    )

    files = result.get(
        "files",
        []
    )

    if not files:

        raise ValueError(
            "Coder returned no files."
        )

    generated_files = {}

    for file_data in files:

        path = file_data.get(
            "path"
        )

        content = file_data.get(
            "content"
        )

        if not path or content is None:

            continue

        generated_files[path] = content

    if not generated_files:

        raise ValueError(
            "Coder returned invalid file data."
        )

    # --------------------------------------------------------
    # Retry counter
    # --------------------------------------------------------

    retry_count = state.get(
        "retry_count",
        0
    )

    state["retry_count"] = retry_count + 1

    # --------------------------------------------------------
    # State
    # --------------------------------------------------------

    state["generated_files"] = (
        generated_files
    )

    # Keep compatibility with
    # single-file downstream code.

    first_path = next(
        iter(generated_files)
    )

    state["active_target_file"] = (
        first_path
    )

    state["generated_code"] = (
        generated_files[first_path]
    )

    return state