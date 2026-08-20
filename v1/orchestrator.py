import os
import requests
from typing import Dict, List, TypedDict
from langgraph.graph import StateGraph, END

# Define local Ollama client configuration
OLLAMA_API = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "phi3.5"

# State Definition (External to LLM prompt context to keep memory small)
class AgentState(TypedDict):
    session_id: int
    current_step: int
    task_checklist: List[Dict]
    active_code: str
    reviewer_feedback: str
    attempts: int

# Memory-Safe Ollama Caller
def call_local_llm(prompt: str, system_prompt: str = "") -> str:
    payload = {
        "model": DEFAULT_MODEL,
        "prompt": prompt,
        "system": system_prompt,
        "stream": False,
        "options": {
            "num_ctx": 4096,      # Guard context limit strictly
            "temperature": 0.2,   # Lower temperature for coding stability
            "num_predict": 1024   # Clamp predictions to avoid runaway tokens
        }
    }
    response = requests.post(OLLAMA_API, json=payload)
    return response.json().get("response", "")

# 1. Supervisor Agent Node (Decomposes complex requests)
def supervisor_node(state: AgentState) -> Dict:
    # Query Postgres to fetch initial request (done via Node -> Python API)
    session_prompt = "Build a lightweight database connection module in Node.js" 
    
    system_instruction = (
        "You are a Project Supervisor. Break down the user prompt into an ordered JSON array of linear steps. "
        "Do not write code. Just generate the tasks."
    )
    
    response = call_local_llm(session_prompt, system_instruction)
    
    # Parse the response to extract tasks
    import json
    task_checklist = json.loads(response)
    
    # Save task checklists to database
    session_id = state['session_id']
    for task in task_checklist:
        task['session_id'] = session_id
        task['status'] = 'pending'
        task['updated_at'] = None
        task['output_schema'] = None
        task['generated_code'] = None
        task['review_notes'] = None
    
    # Insert tasks into the database
    import psycopg2
    conn = psycopg2.connect(
        user="postgres",
        password="your_password",
        host="localhost",
        port="5432",
        dbname="agent_orchestrator"
    )
    cur = conn.cursor()
    for task in task_checklist:
        cur.execute(
            "INSERT INTO tasks_checklist (session_id, step_number, task_name, description, dependencies, status, output_schema, generated_code, review_notes, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (task['session_id'], task['step_number'], task['task'], task['description'], task.get('dependencies', None), task['status'], task['output_schema'], task['generated_code'], task['review_notes'], task['updated_at'])
        )
    conn.commit()
    cur.close()
    conn.close()
    
    # Set up next step
    state['current_step'] = 1
    state['task_checklist'] = task_checklist
    
    return state

# 2. Architect Agent Node (Designs schemas and contracts)
def architect_node(state: AgentState) -> Dict:
    # "Message Stripping": Only pass target task specifications, not supervisor's logs
    current_task = state["task_checklist"][state["current_step"] - 1]
    
    prompt = f"Design the schema and input parameters for: {current_task['task']}"
    system_instruction = "You are an Architect. Produce only specifications, interfaces, or mock databases in JSON."
    
    response = call_local_llm(prompt, system_instruction)
    
    # Save output to database 'tasks_checklist' here...
    import psycopg2
    conn = psycopg2.connect(
        user="postgres",
        password="your_password",
        host="localhost",
        port="5432",
        dbname="agent_orchestrator"
    )
    cur = conn.cursor()
    cur.execute(
        "UPDATE tasks_checklist SET output_schema = %s WHERE session_id = %s AND step_number = %s",
        (response, state['session_id'], state['current_step'])
    )
    conn.commit()
    cur.close()
    conn.close()

    state['active_code'] = response
    
    # return {"active_code": response}
    return state

# 3. Coder Agent Node (Generates isolated modular code blocks)
def coder_node(state: AgentState) -> Dict:
    # Pass only the direct Architect specifications and target output, keeping context windows minimal
    architect_output = state["active_code"]
    
    prompt = f"Based on these specs, write the isolated code block:\n{architect_output}"
    system_instruction = "You are a software engineer. Write clean, modular, production-ready code. Output only raw code."
    
    response = call_local_llm(prompt, system_instruction)
    
    # Save output to database 'tasks_checklist' here...
    import psycopg2
    conn = psycopg2.connect(
        user="postgres",
        password="your_password",
        host="localhost",
        port="5432",
        dbname="agent_orchestrator"
    )
    cur = conn.cursor()
    cur.execute(
        "UPDATE tasks_checklist SET generated_code = %s WHERE session_id = %s AND step_number = %s",
        (response, state['session_id'], state['current_step'])
    )
    conn.commit()
    cur.close()
    conn.close()
    
    state["attempts"] += 1

    state['active_code'] = response

    return state
    # return {"active_code": response, "attempts": state["attempts"] + 1}

# 4. Reviewer/Tester Agent Node (Validates output)
def reviewer_node(state: AgentState) -> Dict:
    code_to_check = state["active_code"]
    
    prompt = f"Analyze this code for syntax correctness:\n{code_to_check}"
    system_instruction = "You are a Reviewer. Return 'PASSED' or point out the specific compilation/syntax bugs."
    
    response = call_local_llm(prompt, system_instruction)
    
    # Save output to database 'tasks_checklist' here...
    import psycopg2
    conn = psycopg2.connect(
        user="postgres",
        password="your_password",
        host="localhost",
        port="5432",
        dbname="agent_orchestrator"
    )
    cur = conn.cursor()
    cur.execute(
        "UPDATE tasks_checklist SET reviewer_feedback = %s WHERE session_id = %s AND step_number = %s",
        (response, state['session_id'], state['current_step'])
    )
    conn.commit()
    cur.close()
    conn.close()

    state['reviwer_feedback'] = response

    return state
    
    # return {"reviewer_feedback": response}

# Define State Machine Routing Logic
def route_after_review(state: AgentState) -> str:
    if "PASSED" in state["reviewer_feedback"] or state["attempts"] >= 3:
        if state['current_step'] < len(state['task_checklist']):
            return "next"
        else:
            return "save_and_flush"
    return "coder"  # Loop back to coder if syntax fails

# Compile State Graph
workflow = StateGraph(AgentState)
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("architect", architect_node)
workflow.add_node("coder", coder_node)
workflow.add_node("reviewer", reviewer_node)

workflow.set_entry_point("supervisor")
workflow.add_conditional_edges("reviewer", route_after_review, {"save_and_flush": END, "coder": "coder", "next": "architect"})
# (Define other transitions...)
app = workflow.compile()