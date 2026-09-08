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

MAX_CONTEXT_CHARS = 12000
MAX_REVIEW_CHARS = 3000


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
            # RTX 3050 safety
            "num_ctx": 4096,

            "temperature": 0.1,

            # Enough for several-file changes
            # without allowing runaway generation.
            "num_predict": 2048,
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

    # Remove markdown fences if model ignores instructions.
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

        raise ValueError(
            "Coder returned invalid JSON."
        )


# ============================================================
# CONTEXT NORMALIZATION
# ============================================================

def build_code_edit_context(
    state: AgentOrchestratorState
) -> str:
    """
    Build the exact source context supplied to the Coder.

    The preferred source is:

        state["sliced_code_context"]

    which should already have been produced by the
    code-graph/context retrieval layer.

    This function deliberately does NOT perform repository-wide
    retrieval. The Coder should not independently discover files.
    """

    context = state.get(
        "sliced_code_context",
        ""
    )

    if not context:
        raise ValueError(
            "Coder received no sliced_code_context. "
            "Architect/context retrieval must provide "
            "implementation code for the target files."
        )

    # Keep the newest/current context bounded.
    if len(context) > MAX_CONTEXT_CHARS:

        context = context[
            :MAX_CONTEXT_CHARS
        ]

        context += (
            "\n\n"
            "[CONTEXT TRUNCATED BY CODER]"
        )

    return context


# ============================================================
# TARGET VALIDATION
# ============================================================

def validate_target_files(
    state: AgentOrchestratorState
):
    """
    Ensure Architect supplied target files.

    Coder must never invent target files.
    """

    target_files = state.get(
        "target_files",
        []
    )

    if not target_files:

        raise ValueError(
            "Coder received no target_files."
        )

    return target_files


# ============================================================
# REVIEW FEEDBACK
# ============================================================

def build_retry_context(
    state: AgentOrchestratorState
) -> str:

    reviewer_feedback = state.get(
        "reviewer_feedback"
    )

    if not reviewer_feedback:
        return ""

    feedback = str(
        reviewer_feedback
    )

    if len(feedback) > MAX_REVIEW_CHARS:

        feedback = feedback[
            :MAX_REVIEW_CHARS
        ]

    return f"""
============================================================
PREVIOUS REVIEW FAILURE
============================================================

{feedback}

============================================================
REPAIR INSTRUCTION
============================================================

Correct the reported failure.

Do not merely explain the failure.

Return the corrected complete file contents.
"""


# ============================================================
# SYSTEM PROMPT
# ============================================================

CODER_SYSTEM_PROMPT = """
You are the CODER AGENT in a multi-agent software engineering
system.

Your responsibility is to implement ONE CURRENT TASK.

You are NOT the planner.

You are NOT the architect.

You are NOT responsible for discovering unrelated files.

You must implement only the files and changes supplied by the
current task and repository context.

============================================================
INPUT CONTRACT
============================================================

You receive:

1. USER REQUIREMENT
2. CURRENT TASK
3. TECHNICAL SPECIFICATION
4. TARGET FILES
5. REPOSITORY CODE CONTEXT
6. OPTIONAL REVIEWER FEEDBACK

The repository code context contains the existing implementation
that must be preserved and modified.

============================================================
SOURCE OF TRUTH
============================================================

For existing files:

The supplied repository code is the source of truth.

Preserve:

- existing imports
- existing classes
- existing functions
- existing behavior
- existing error handling
- existing public APIs
- existing unrelated code

Make the smallest change required by the current task.

Do NOT rewrite an entire architecture when a local modification
is sufficient.

============================================================
TARGET FILE RULE
============================================================

Only modify files explicitly listed in TARGET FILES or CURRENT
TASK.

Do NOT create additional files unless the current task explicitly
requires them.

Do NOT modify unrelated files.

Do NOT invent file paths.

============================================================
CODE CONTEXT RULE
============================================================

Repository context may contain:

- complete files
- relevant symbols
- surrounding implementation
- imports
- dependency information
- related symbols

Use the supplied implementation context.

If existing code is supplied, preserve it.

Do NOT replace existing implementation with a simplified example.

============================================================
MULTI-FILE CHANGES
============================================================

When multiple files are supplied:

- understand their relationships
- preserve interfaces between them
- keep imports consistent
- keep method signatures compatible
- keep API contracts consistent

============================================================
REVIEW FEEDBACK
============================================================

If reviewer feedback is provided:

Fix the reported problem.

Do not merely describe the problem.

Do not remove functionality just to make compilation pass.

============================================================
OUTPUT CONTRACT
============================================================

Return ONLY valid JSON.

The JSON MUST have exactly this top-level structure:

{
  "generated_files": {
    "path/to/file.ts": "complete file content",
    "path/to/another.ts": "complete file content"
  }
}

The generated_files object maps:

FILE PATH -> COMPLETE FILE CONTENT

============================================================
CRITICAL OUTPUT RULES
============================================================

Return complete file contents.

DO NOT return snippets.

DO NOT return patches.

DO NOT return diffs.

DO NOT return Markdown.

DO NOT return code fences.

DO NOT return explanations.

DO NOT return comments outside generated source files.

DO NOT return AgentOrchestratorState.

DO NOT return task_checklist.

DO NOT return technical_spec.

DO NOT return reviewer_feedback.

First character must be:

{

Last character must be:

}

============================================================
FINAL CHECK
============================================================

Before responding verify:

1. JSON is valid.
2. generated_files exists.
3. generated_files is an object.
4. Every target file that requires modification is present.
5. Every generated value is complete source code.
6. No Markdown fences exist.
7. No explanations exist.
"""


# ============================================================
# PROMPT
# ============================================================

def build_coder_prompt(
    state: AgentOrchestratorState,
    code_context: str,
    target_files
) -> str:

    current_task = state.get(
        "current_task"
    )

    if not current_task:

        raise ValueError(
            "Coder received no current_task."
        )

    technical_spec = state.get(
        "technical_spec",
        ""
    )

    retry_context = build_retry_context(
        state
    )

    return f"""
============================================================
USER REQUIREMENT
============================================================

{state["user_requirement"]}


============================================================
CURRENT TASK
============================================================

{json.dumps(
    current_task,
    indent=2
)}


============================================================
TECHNICAL SPECIFICATION
============================================================

{technical_spec}


============================================================
TARGET FILES
============================================================

{json.dumps(
    target_files,
    indent=2
)}


============================================================
REPOSITORY IMPLEMENTATION CONTEXT
============================================================

{code_context}


{retry_context}


============================================================
IMPLEMENTATION INSTRUCTION
============================================================

Implement ONLY the current task.

Use the repository implementation context as the source of
truth for existing files.

Preserve unrelated implementation.

Make the smallest correct changes.

Return complete contents for every modified file.

Return JSON ONLY.
"""


# ============================================================
# GENERATED FILE VALIDATION
# ============================================================

def validate_generated_files(
    result: Dict[str, Any]
) -> Dict[str, str]:

    generated_files = result.get(
        "generated_files"
    )

    if not isinstance(
        generated_files,
        dict
    ):

        raise ValueError(
            "Coder returned invalid generated_files. "
            "Expected an object mapping file paths "
            "to complete file contents."
        )

    if not generated_files:

        raise ValueError(
            "Coder returned no generated files."
        )

    clean_files = {}

    for path, content in generated_files.items():

        if not isinstance(
            path,
            str
        ) or not path.strip():

            continue

        if not isinstance(
            content,
            str
        ):

            raise ValueError(
                f"Generated content for '{path}' "
                "is not a string."
            )

        if not content.strip():

            raise ValueError(
                f"Generated file '{path}' "
                "contains empty content."
            )

        clean_files[
            path
        ] = content

    if not clean_files:

        raise ValueError(
            "Coder returned no valid generated files."
        )

    return clean_files


# ============================================================
# CODER NODE
# ============================================================

def run_coder(
    state: AgentOrchestratorState
):

    # --------------------------------------------------------
    # Current task
    # --------------------------------------------------------

    current_task = state.get(
        "current_task"
    )

    if not current_task:

        raise ValueError(
            "Coder received no current_task."
        )

    # --------------------------------------------------------
    # Target files
    # --------------------------------------------------------

    target_files = validate_target_files(
        state
    )

    # --------------------------------------------------------
    # Actual source implementation context
    # --------------------------------------------------------

    code_context = build_code_edit_context(
        state
    )

    # --------------------------------------------------------
    # Build prompt
    # --------------------------------------------------------

    prompt = build_coder_prompt(
        state=state,
        code_context=code_context,
        target_files=target_files
    )

    # --------------------------------------------------------
    # Call model
    # --------------------------------------------------------

    response = call_local_llm(
        prompt,
        CODER_SYSTEM_PROMPT
    )

    if not response:

        raise RuntimeError(
            "Coder Ollama response was empty."
        )

    # --------------------------------------------------------
    # Parse JSON
    # --------------------------------------------------------

    print(code_context)
    print(target_files)
    print(response)


    result = extract_json(
        response
    )

    # --------------------------------------------------------
    # Validate contract
    # --------------------------------------------------------

    generated_files = (
        validate_generated_files(
            result
        )
    )

    # --------------------------------------------------------
    # Retry counter
    # --------------------------------------------------------

    retry_count = state.get(
        "retry_count",
        0
    )

    state["retry_count"] = (
        retry_count + 1
    )

    # --------------------------------------------------------
    # Store generated files
    # --------------------------------------------------------

    state["generated_files"] = (
        generated_files
    )

    # --------------------------------------------------------
    # Backwards compatibility
    # --------------------------------------------------------

    first_path = next(
        iter(generated_files)
    )

    state["active_target_file"] = (
        first_path
    )

    state["generated_code"] = (
        generated_files[first_path]
    )

    # --------------------------------------------------------
    # Clear stale reviewer feedback
    #
    # Only clear it after the coder has consumed it.
    # --------------------------------------------------------

    state["reviewer_feedback"] = None

    return state