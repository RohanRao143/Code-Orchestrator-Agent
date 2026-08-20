from app_context import init_context
from orchestrator import app


# ============================================================
# INDEX PROJECT
# ============================================================

project_id = init_context([
    "./backend",
    "./frontend",
    "./database",
])


# ============================================================
# USER REQUIREMENT
# ============================================================

requirement = """
Add audit logging to all authenticated API requests.

Store:

- user ID
- endpoint
- HTTP method
- timestamp
- response status

in PostgreSQL.
"""


# ============================================================
# START ORCHESTRATOR
# ============================================================

result = app.invoke({
    "user_requirement": requirement,

    "context_project_id": project_id,

    "current_task_index": 0,
})