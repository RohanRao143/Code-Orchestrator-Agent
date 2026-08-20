# Unified Multi-Agent State Orchestration Flow (v2)

This blueprint details the technical implementation of your local development pipeline (**Angular, Node.js, Postgres, Ollama**). It integrates the architectural principles from your technical sources, specifically the **Hierarchical Multi-Agent Orchestration Layer** [1, 15], **Model Context Protocol (MCP)** [15, 37], and **Agent-to-Agent (A2A) communication protocols** [15, 40] to build a memory-safe, crash-resistant software factory on entry-level hardware [1, 15].

---

## 1. Core Structural Architecture & Protocols

Your multi-agent environment is governed by two complementary communication protocols and an orchestration control plane [15]:

```
   ┌────────────────────────────────────────────────────────────────────────┐
   │                       ORCHESTRATION LAYER (Control Plane)              │
   │  ┌───────────────────────┐ ┌─────────────────────────┐ ┌────────────┐  │
   │  │ Planning & Policies   │ │ State & Knowledge Mgmt  │ │ Quality &  │  │
   │  │ (Supervisor Planning) │ │ (PostgreSQL / SQLite)   │ │ Operations │  │
   │  └───────────────────────┘ └─────────────────────────┘ └────────────┘  │
   └─────────────┬───────────────────────────┬─────────────────────┬────────┘
                 │ (A2A Protocol)            │ (A2A Protocol)      │ (A2A Protocol)
                 ▼                           ▼                     ▼
        ┌─────────────────┐         ┌─────────────────┐   ┌─────────────────┐
        │  Worker Agent   │         │  Service Agent  │   │  Support Agent  │
        │  (Coder Node)   │         │ (Reviewer Node) │   │ (Observability) │
        └────────┬────────┘         └────────┬────────┘   └────────┬────────┘
                 │                           │                     │
                 │ (MCP Protocol Client)     │ (MCP Protocol Client)│ (MCP Protocol)
                 ▼                           ▼                     ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                          MODEL CONTEXT PROTOCOL (MCP)                  │
   │   ┌────────────────────┐     ┌─────────────────────┐    ┌──────────┐   │
   │   │  Code Slicer Tool  │     │ Compiler / Test CLI │    │ Postgres │   │
   │   │    (MCP Server)    │     │    (MCP Server)     │    │   RAG    │   │
   │   └────────────────────┘     └─────────────────────┘    └──────────┘   │
   └────────────────────────────────────────────────────────────────────────┘
```

1. **The Orchestration Layer**: Oversees planning, state management, and quality operations [15, 45]. It maintains consistency across nodes and synchronizes active progress to PostgreSQL [31, 35].
2. **Model Context Protocol (MCP)**: Standardizes how agents query external data, read and modify code, and run compilers [15, 36, 37]. The agents act as **MCP Clients** invoking registered **MCP Servers** (tools) through structured JSON-RPC calls, ensuring strict security boundaries and schema validation [37, 38].
3. **Agent-to-Agent (A2A) Protocol**: Standardizes negotiation, delegation, and feedback between specialized agents [15, 40]. When the **Reviewer Node (Service Agent)** identifies code execution or syntax errors, it uses the A2A protocol to send structured diagnostics and error contexts directly back to the **Coder Node (Worker Agent)** [26, 41].

---

## 2. Global Orchestration State

In a sequential state machine design (using LangGraph), the global state is captured in a Python dictionary and backed up to **PostgreSQL** to prevent VRAM crash loss [1, 2, 5, 31]. 

```python
# state_schema.py
from typing import TypedDict, List, Dict, Optional, Any

class AgentOrchestratorState(TypedDict):
    # Workflow Metadata
    workflow_id: str                    # Unique execution UUID
    user_requirement: str               # Core instruction from Angular
    
    # State & Planning (Planning Unit)
    task_checklist: List[Dict[str, Any]]# Detailed list of sub-tasks
    current_task_index: int             # Pointer to current checklist item
    
    # Context & Resources (MCP Slicing & Code Discovery)
    target_files: List[str]             # File paths modified/accessed by active task
    sliced_code_context: str            # Interface signatures/contracts (token-safe)
    technical_spec: str                 # Unified schema, routes, contracts contract
    
    # Coder Execution (Worker Agent Node)
    active_target_file: str             # The file currently being written
    generated_code: str                 # Code block written by Coder Agent
    
    # Quality & Operations (Service/Support Validation)
    compilation_status: str             # "PENDING", "SUCCESS", "FAILED"
    reviewer_feedback: Optional[str]    # Compiler/syntax checker error traceback
    retry_count: int                    # Self-correction loop count (capped at 2)
```

---

## 3. Node-by-Node Pipeline, Contracts, and Core Scripts

Below is the redefined, end-to-end multi-agent orchestration workflow. Each node shows its **upstream inputs**, **downstream outputs**, **exact JSON data contracts**, and the corresponding **integration scripts**.

### Phase 1: The State Phase (Supervisor & Planning Node)
*   **Specialized Role**: **Planning and Policy Unit** [29]
*   **Responsibilities**:
    *   Initialize the global workflow execution entry in PostgreSQL [31].
    *   Query the PostgreSQL codebase file index using an **MCP database tool** to find existing files relevant to the prompt [38].
    *   Decompose the user request into an isolated, sequential checklist of sub-tasks to restrict prompt context size [1, 29].
    *   Enforce system-level limits (e.g. limiting files affected to prevent context OOM) [2, 29].

```
┌─────────────────┐             ┌─────────────────────┐             ┌─────────────────────────┐
│  Web UI Request ├────────────►│  The State Phase    ├────────────►│   Architect Discovery   │
│ (User Prompt)   │             │  (Supervisor Node)  │             │          Node           │
└─────────────────┘             └──────────┬──────────┘             └─────────────────────────┘
                                           │
                                           ▼
                                ┌─────────────────────┐
                                │ PostgreSQL State DB │
                                └─────────────────────┘
```

#### Upstream Input Contract (From Angular/Node Express Backend):
```json
{
  "workflow_id": "8fa3c0e1-7d12-42ef-93a8-4221da0fa0a2",
  "user_requirement": "Add a feature to log system audits in an 'audit_logs' table, build a Node API route POST /api/audit to save logs, and write an Angular service to invoke it."
}
```

#### Downstream Output Contract (To State & Database):
```json
{
  "workflow_id": "8fa3c0e1-7d12-42ef-93a8-4221da0fa0a2",
  "current_task_index": 0,
  "task_checklist": [
    {
      "step_id": 1,
      "domain": "postgres",
      "description": "Create 'audit_logs' table schema with columns id, user_id, action, timestamp.",
      "files_affected": ["db/schema.sql"]
    },
    {
      "step_id": 2,
      "domain": "node_express",
      "description": "Implement Express router endpoint POST /api/audit to write logs.",
      "files_affected": ["routes/audit.js"]
    },
    {
      "step_id": 3,
      "domain": "angular",
      "description": "Create an Angular log-monitoring service to invoke the Express endpoint.",
      "files_affected": ["src/app/services/audit.service.ts"]
    }
  ]
}
```

#### Upstream/Downstream Script Hook (`supervisor.py`):
```python
# supervisor.py
import sys
import json
import psycopg2
from typing import Dict, Any

def run_supervisor(workflow_id: str, user_requirement: str) -> Dict[str, Any]:
    # 1. Access DB using standard context to locate matching files
    conn = psycopg2.connect("dbname=agentdb user=postgres password=secret host=localhost")
    cursor = conn.cursor()
    
    # 2. Compile system prompt with codebase catalog metadata
    system_prompt = (
        "You are the Planning & Policy Unit. Decompose the user request into sequential steps. "
        "Each step must affect minimal files. Output JSON ONLY matching the task_checklist format."
    )
    
    # 3. Invoke local model via Ollama (e.g., Phi-3.5-mini-instruct)
    # response = ollama.generate(model='phi3.5:latest', prompt=...)
    # Mock result matching the contract:
    task_checklist = [
        {"step_id": 1, "domain": "postgres", "description": "Create 'audit_logs' table schema...", "files_affected": ["db/schema.sql"]},
        {"step_id": 2, "domain": "node_express", "description": "Implement Express router...", "files_affected": ["routes/audit.js"]},
        {"step_id": 3, "domain": "angular", "description": "Create Angular service...", "files_affected": ["src/app/services/audit.service.ts"]}
    ]
    
    # 4. Save checklist to PostgreSQL to update Global State
    cursor.execute(
        "INSERT INTO agent_workflows (workflow_id, user_requirement, current_status, current_task_index) "
        "VALUES (%s, %s, 'ACTIVE', 0) ON CONFLICT (workflow_id) DO UPDATE SET current_task_index = 0;",
        (workflow_id, user_requirement)
    )
    for step in task_checklist:
        cursor.execute(
            "INSERT INTO agent_tasks (workflow_id, step_number, domain, task_description, files_affected, status) "
            "VALUES (%s, %s, %s, %s, %s, 'PENDING');",
            (workflow_id, step["step_id"], step["domain"], step["description"], step["files_affected"])
        )
    conn.commit()
    cursor.close()
    conn.close()
    
    return {
        "workflow_id": workflow_id,
        "task_checklist": task_checklist,
        "current_task_index": 0
    }

if __name__ == "__main__":
    # Standard CLI wrapper to receive JSON inputs from Node process
    input_data = json.loads(sys.stdin.read())
    output = run_supervisor(input_data["workflow_id"], input_data["user_requirement"])
    print(json.dumps(output))
```

---

### Phase 2: The Architect Discovery Node
*   **Specialized Role**: **Execution & Knowledge Management Unit** [30, 31]
*   **Responsibilities**:
    *   Retrieve the single active checklist task using the `current_task_index` [1, 7].
    *   Query the file systems for `files_affected` via **MCP Tool Calls** to read actual files [37, 38].
    *   Run `slicer.py` (serving as an **MCP Server**) on those files to strip heavy implementation logic, preserving only interfaces, endpoint contracts, and model declarations [15, 38]. This guarantees the context window fits within **4,096 tokens** [2].
    *   Construct a detailed technical execution spec (API route JSON parameters, typescript signatures) defining the change [4].

```
┌─────────────────────┐             ┌─────────────────────────┐             ┌────────────────┐
│  The State Phase    ├────────────►│   Architect Discovery   ├────────────►│   Coder Node   │
│ (Supervisor Node)   │             │          Node           │             │ (Worker Agent) │
└─────────────────────┘             └────────────┬────────────┘             └────────────────┘
                                                 │
                             Calls MCP Tool      ▼
                         ┌────────────────────────────────┐
                         │ MCP Code Slicer Server (Local) │
                         └────────────────────────────────┘
```

#### Upstream Input Contract (From global state & active DB record):
```json
{
  "workflow_id": "8fa3c0e1-7d12-42ef-93a8-4221da0fa0a2",
  "current_task": {
    "step_id": 2,
    "domain": "node_express",
    "description": "Implement Express router endpoint POST /api/audit to write logs.",
    "files_affected": ["routes/audit.js"]
  }
}
```

#### Downstream Output Contract (Passed as context for coding):
```json
{
  "target_files": ["routes/audit.js"],
  "sliced_code_context": "// routes/audit.js \nconst express = require('express');\nconst router = express.Router();\n// Existing routes stripped...\nmodule.exports = router;",
  "technical_spec": "Write a POST router '/api/audit' that accepts { userId: string, action: string } in request body, writes to postgres, and returns 201 JSON status { success: true, logId: string }."
}
```

#### Upstream/Downstream Script Hook (`architect.py`):
```python
# architect.py
import sys
import json
import os
from typing import Dict, Any

def run_architect(task_payload: Dict[str, Any]) -> Dict[str, Any]:
    workflow_id = task_payload["workflow_id"]
    current_task = task_payload["current_task"]
    files_affected = current_task["files_affected"]
    
    sliced_contexts = []
    # Loop over affected files and call Slicer as an MCP Tool simulation
    for file_path in files_affected:
        if os.path.exists(file_path):
            # MCP-Client style file-reading tool call
            with open(file_path, 'r') as f:
                raw_code = f.read()
            # Perform programmatic slicing (Regex or AST) to cut method bodies
            sliced_code = slice_file_structure(raw_code, file_path)
            sliced_contexts.append(f"// FILE: {file_path}\n{sliced_code}")
        else:
            sliced_contexts.append(f"// FILE: {file_path} (File will be created)")

    sliced_code_context = "\n".join(sliced_contexts)
    
    # Core LLM prompt for technical specification design (Knowledge Unit)
    # Generates strict specs under 4,096 context window
    technical_spec = (
        f"Design an implementation spec for task: {current_task['description']}\n"
        f"Target signatures:\n{sliced_code_context}"
    )
    
    # Mock return spec generated by LLM (Ollama Phi-3.5)
    resolved_spec = (
        "Create POST route /api/audit. Extract req.body.userId and req.body.action. "
        "Perform pool.query('INSERT INTO audit_logs (user_id, action) VALUES ($1, $2)'). "
        "Send 201 response JSON."
    )
    
    return {
        "target_files": files_affected,
        "sliced_code_context": sliced_code_context,
        "technical_spec": resolved_spec
    }

def slice_file_structure(raw_code: str, file_path: str) -> str:
    # Programmatic slicing utility (Helper)
    lines = raw_code.splitlines()
    if file_path.endswith('.ts') or file_path.endswith('.js'):
        # Keep only class signatures, imports, and function contracts
        return "\n".join([l for l in lines if "class" in l or "export" in l or "require" in l or "import" in l or "Router" in l])
    return raw_code

if __name__ == "__main__":
    input_data = json.loads(sys.stdin.read())
    output = run_architect(input_data)
    print(json.dumps(output))
```

---

### Phase 3: The Coder Node
*   **Specialized Role**: **Worker Agent (Stateless Execution)** [25]
*   **Responsibilities**:
    *   Wipe the active Ollama context engine to guarantee maximum GPU VRAM overhead before running [2, 8].
    *   Construct a stripped-down, focused prompt containing *only* the output from the Architect and the targeted code slice (**Message Stripping**) [6]. The Supervisor’s organizational workflow reasoning is entirely hidden to protect memory boundaries [6].
    *   Generate clean, functional code targeted at the exact file [4, 25].

```
┌─────────────────────────┐             ┌─────────────────┐             ┌──────────────────┐
│   Architect Discovery   ├────────────►│   Coder Node    ├────────────►│  Reviewer Node   │
│          Node           │             │ (Worker Agent)  │             │ (Service Agent)  │
└─────────────────────────┘             └────────┬────────┘             └──────────────────┘
                                                 │
                                Wipes VRAM First ▼
                                ┌────────────────────────────────┐
                                │ Ollama /clear (Fresh Memory)   │
                                └────────────────────────────────┘
```

#### Upstream Input Contract (Formed by strict context assembly):
```json
{
  "target_file_path": "routes/audit.js",
  "sliced_code_context": "const express = require('express');\nconst router = express.Router();\nmodule.exports = router;",
  "technical_spec": "Create POST route /api/audit. Extract req.body.userId and req.body.action. Query database. Return 201 status.",
  "reviewer_feedback": null
}
```

#### Downstream Output Contract (Generated block to be written to staging):
```json
{
  "target_file_path": "routes/audit.js",
  "generated_code": "const express = require('express');\nconst router = express.Router();\nconst pool = require('../db/pool');\n\nrouter.post('/api/audit', async (req, res) => {\n  const { userId, action } = req.body;\n  try {\n    const result = await pool.query('INSERT INTO audit_logs (user_id, action) VALUES ($1, $2) RETURNING id', [userId, action]);\n    res.status(201).json({ success: true, logId: result.rows[0].id });\n  } catch (err) {\n    res.status(500).json({ error: err.message });\n  }\n});\n\nmodule.exports = router;"
}
```

#### Upstream/Downstream Script Hook (`coder.py`):
```python
# coder.py
import sys
import json
import requests
from typing import Dict, Any

def run_coder(payload: Dict[str, Any]) -> Dict[str, Any]:
    # 1. Clear local Ollama VRAM canvas prior to generating heavy code blocks
    # Prevents OOM failures under 4GB local limits
    try:
        requests.post("http://localhost:11434/api/generate", json={"model": "stable-code:latest", "keep_alive": 0})
    except Exception:
        pass # Ignore if local server is busy or direct-invoked
        
    # 2. Extract inputs (Message Stripping)
    target_file = payload["target_file_path"]
    sliced_code = payload["sliced_code_context"]
    tech_spec = payload["technical_spec"]
    feedback = payload.get("reviewer_feedback")
    
    # 3. Formulate minimal engineering prompt
    prompt = (
        f"Task Contract: {tech_spec}\n"
        f"Original File Structure:\n{sliced_code}\n"
    )
    if feedback:
        # If running in a self-correction loopback
        prompt += f"\nCORRECTION REQUIRED. Prior validation failed with error:\n{feedback}\nFix this specific error."

    # 4. Invoke local code generator LLM (Stable-Code-3B or Phi-3.5-mini-instruct)
    # response = ollama.generate(model='stable-code', prompt=prompt)
    
    # Mocking successful generation corresponding to contract
    generated_code = (
        "const express = require('express');\n"
        "const router = express.Router();\n"
        "const pool = require('../db/pool');\n"
        "router.post('/api/audit', async (req, res) => {\n"
        "  const { userId, action } = req.body;\n"
        "  try {\n"
        "    const result = await pool.query('INSERT INTO audit_logs (user_id, action) VALUES ($1, $2) RETURNING id', [userId, action]);\n"
        "    res.status(201).json({ success: true, logId: result.rows[0].id });\n"
        "  } catch (err) {\n"
        "    res.status(500).json({ error: err.message });\n"
        "  }\n"
        "});\n"
        "module.exports = router;"
    )
    
    return {
        "target_file_path": target_file,
        "generated_code": generated_code
    }

if __name__ == "__main__":
    input_data = json.loads(sys.stdin.read())
    output = run_coder(input_data)
    print(json.dumps(output))
```

---

### Phase 4: The Reviewer Node
*   **Specialized Role**: **Service Agent (QA & Compliance Validator)** [26]
*   **Responsibilities**:
    *   Temporarily write the generated code to a local workspace sandbox path.
    *   Execute local compiler/interpreter system subprocesses (e.g. `node --check` for Node.js, `npx tsc --noEmit` for Angular) to validate compilation status [33, 44].
    *   **A2A Error Loop**: If syntax checks fail, format the raw terminal tracebacks and invoke the **A2A protocol** to loop execution back to the Coder Agent [26, 41]. Increment the retry tracker [44].
    *   **Task Continuity**: If the checks pass successfully, commit the changes to the physical codebase directory, increment `current_task_index`, reset the error retry counts, and proceed to the next step [31, 33].

```
                                              ┌──────────────────┐
                                              │  Reviewer Node   │
                                              │ (Service Agent)  │
                                              └────────┬─────────┘
                                                       │
                                            Runs       ▼
                                ┌────────────────────────────────┐
                                │ TypeScript / Node CLI Compiler │
                                └──────────────┬─────────────────┘
                                               │
                       ┌───────────────────────┴───────────────────────┐
                       │ Fail                                          │ Pass
                       ▼                                               ▼
          ┌─────────────────────────┐                     ┌─────────────────────────┐
          │     Loop to Coder       │                     │    Commit file to disk  │
          │ (A2A Diagnostics Error) │                     │    & advance workflow   │
          └─────────────────────────┘                     └─────────────────────────┘
```

#### Upstream Input Contract (From Coder Node):
```json
{
  "workflow_id": "8fa3c0e1-7d12-42ef-93a8-4221da0fa0a2",
  "target_file_path": "routes/audit.js",
  "generated_code": "const express = require('express');\nconst router = express.Router();\n...",
  "retry_count": 0
}
```

#### Downstream Output Contract (Loops back to Coder OR triggers success commits):
*   **On SUCCESS Validation**:
    ```json
    {
      "compilation_status": "SUCCESS",
      "reviewer_feedback": null,
      "increment_task": true,
      "reset_retry": true
    }
    ```
*   **On FAILURE Validation**:
    ```json
    {
      "compilation_status": "FAILED",
      "reviewer_feedback": "SyntaxError: Unexpected identifier in routes/audit.js at Line 5: const pool = req..",
      "increment_task": false,
      "reset_retry": false
    }
    ```

#### Upstream/Downstream Script Hook (`reviewer.py`):
```python
# reviewer.py
import sys
import json
import subprocess
import os
from typing import Dict, Any

def run_reviewer(payload: Dict[str, Any]) -> Dict[str, Any]:
    workflow_id = payload["workflow_id"]
    target_file = payload["target_file_path"]
    code_content = payload["generated_code"]
    retry_count = payload.get("retry_count", 0)
    
    # 1. Write the code to a temporary path (staging check)
    temp_file = f"/workspace/scratch/{os.path.basename(target_file)}"
    os.makedirs(os.path.dirname(temp_file), exist_ok=True)
    with open(temp_file, 'w') as f:
        f.write(code_content)
        
    # 2. Run Compiler verification based on file domain
    compilation_error = None
    if target_file.endswith('.js'):
        # Node.js syntax verification
        result = subprocess.run(['node', '--check', temp_file], capture_output=True, text=True)
        if result.returncode != 0:
            compilation_error = result.stderr or "Syntax verification failed."
            
    elif target_file.endswith('.ts'):
        # TypeScript/Angular non-emit compile check
        result = subprocess.run(['npx', 'tsc', '--noEmit', temp_file], capture_output=True, text=True)
        if result.returncode != 0:
            compilation_error = result.stdout or result.stderr or "TS Compile error."

    # 3. Dynamic Output Evaluation (Quality & Operations Management)
    if compilation_error:
        # Return failing loop contract (will loop back to Coder via LangGraph)
        return {
            "compilation_status": "FAILED",
            "reviewer_feedback": compilation_error,
            "increment_task": False,
            "reset_retry": False
        }
    else:
        # Move successfully validated file from temporary staging to physical codebase path
        os.makedirs(os.path.dirname(target_file), exist_ok=True)
        with open(target_file, 'w') as f:
            f.write(code_content)
            
        return {
            "compilation_status": "SUCCESS",
            "reviewer_feedback": None,
            "increment_task": True,
            "reset_retry": True
        }

if __name__ == "__main__":
    input_data = json.loads(sys.stdin.read())
    output = run_reviewer(input_data)
    print(json.dumps(output))
```

---

## 4. Operational Handoff Data Pipeline Summary

The following index maps how raw parameters transition between scripts, and how values are saved to the database at each execution checkpoint.

| Action Step | Node Execution | Native Input | Produced Output | Saved State/DB Action | Memory/VRAM Guard |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Step 1** | **The State Phase** (`supervisor.py`) | User raw requirements prompt | Array of structured checklist sub-tasks | Insert new workflow in `agent_workflows` and checklist steps in `agent_tasks`. | **Flush previous session context** before analyzing requirements. |
| **Step 2** | **Architect Discovery** (`architect.py`) | Active task detail row from `agent_tasks` | `sliced_code_context` and parsed functional parameters | Write `technical_spec` contract to database. | **AST / Slicing filter** restricts file readings to signatures only (under 4k limits). |
| **Step 3** | **Coder Node** (`coder.py`) | Active spec and target file signature | New file code output | Stage raw code in database for review. | **Ollama `/clear` VRAM flush** is triggered before executing code generation. |
| **Step 4** | **Reviewer Node** (`reviewer.py`) | Raw generated code content and target path | Success or failure feedback payload | If **SUCCESS**: Save file to workspace, update database row status to `COMPLETED`. If **FAILED**: Increment task retry counters. | Run CLI processes locally (saving VRAM). Wipes memory canvas clean on task completion. |
