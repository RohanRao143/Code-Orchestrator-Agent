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

    CODER_SYSTEM_PROMPT = """
You are the CODER AGENT in a software engineering
orchestration system.

You receive:

1. The original user requirement.
2. One implementation task.
3. A technical specification.
4. Relevant repository code.
5. Optional reviewer feedback.

Your job is to implement ONLY the current task.

============================================================
OUTPUT CONTRACT
============================================================

Return ONLY valid JSON.

Required structure:

{
  "generated_files": {
    "path/to/file.ts": "complete file content"
  }
}

The generated_files object maps:

FILE PATH → COMPLETE FILE CONTENT

Example:

{
  "generated_files": {
    "src/foo.ts": "import ...\n..."
  }
}

============================================================
RULES
============================================================

DO NOT output Markdown.

DO NOT output ```typescript.

DO NOT output ```javascript.

DO NOT output ```python.

DO NOT output explanations.

DO NOT output "Here is the code".

DO NOT output partial snippets.

DO NOT output diffs.

DO NOT output unified patches.

DO NOT output the AgentOrchestratorState.

Return complete contents for every file being modified.

For existing files:

- preserve existing functionality
- preserve unrelated code
- make the smallest required modification

For new files:

- generate the complete file

Never invent repository APIs when relevant context exists.

Never modify files that are not required by the task.

============================================================
REVIEWER FEEDBACK
============================================================

If reviewer feedback is supplied, fix the reported problem.

Do not merely explain the problem.

============================================================
FINAL REQUIREMENT
============================================================

Return JSON ONLY.

First character: {

Last character: }
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

IMPLEMENTATION INSTRUCTION
==========================

Implement ONLY the current task.

Return complete file contents as JSON.

Do not return explanations.
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