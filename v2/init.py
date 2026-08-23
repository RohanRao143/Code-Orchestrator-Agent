from app_context import init_context_code_graph
from orchestrator import app

from app_context import visualize_ui_graph


# ============================================================
# INDEX PROJECT
# ============================================================

# project_id = init_context([
#     "./backend",
#     "./frontend",
#     "./database",
# ])

project_id = init_context_code_graph([
    "../../../Repo-0011-BeED-UI"
])

# visualize_ui_graph(
#     project_id=project_id
# )

# ============================================================
# USER REQUIREMENT
# ============================================================

# requirement = """
# Add audit logging to all authenticated API requests.

# Store:

# - user ID
# - endpoint
# - HTTP method
# - timestamp
# - response status

# in PostgreSQL.
# """

requirement = """
In the file learner-feedback.component.ts, Add soft property isHidden for each stage object in learner feedback page, when isHidden set to true the table should hide all the lesson blocks under that stage. clicking on the stage header should work like a toggle. 
"""



# ============================================================
# START ORCHESTRATOR
# ============================================================

result = app.invoke({
    "user_requirement": requirement,

    "context_project_id": project_id,

    "current_task_index": 0,
})