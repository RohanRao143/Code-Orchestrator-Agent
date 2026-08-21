from app_context import init_context
from orchestrator import app


# ============================================================
# INDEX PROJECT
# ============================================================

# project_id = init_context([
#     "./backend",
#     "./frontend",
#     "./database",
# ])

project_id = init_context([
    "../../../Repo-0011-BeED-UI"
])


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
Add enable preview option inside experio over oview settings, with a preview icon and a toggle button.

Enabling it should send preview_enabled boolean option property to api 
"""



# ============================================================
# START ORCHESTRATOR
# ============================================================

result = app.invoke({
    "user_requirement": requirement,

    "context_project_id": project_id,

    "current_task_index": 0,
})