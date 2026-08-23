The inconsistency in your supervisor agent's output is a common issue in multi-agent LLM systems. It usually happens due to non-deterministic semantic retrieval (RAG) combined with an unstructured context injection format. [1] 
Because you are chunking files and using embeddings (vector(1536)), the agent relies heavily on vector similarity search to find out which files are relevant to a plain requirement.
Here is a breakdown of why this is happening and how to fix it.
------------------------------
## Why the Files Affected Keep Changing## 1. Semantic Drift & Vector Thresholds

* The Issue: Plain requirements use high-level words (e.g., "Add user authentication").
* The Result: The semantic search returns slightly different chunks depending on how close the embeddings are. If 5 files are relevant, a tiny shift in top-k retrieval might pull files A, B, C on run one, and B, C, D on run two.

## 2. Cross-Chunk Context Fragmentation

* The Issue: Your database splits code into arbitrary lines (start_line to end_line).
* The Result: Class definitions might be in Chunk 1, but their implementations are in Chunk 2. The supervisor agent gets a fragmented view of the codebase, leading to different logical conclusions every time.

## 3. State/Code Asymmetry

* The Issue: Code contains internal relationships (imports, inheritance) that flat text chunks ignore.
* The Result: The agent cannot map out dependencies accurately. It "guesses" the affected files based on raw text similarity instead of actual structural relationships. [2] 

------------------------------
## How to Fix It
To achieve consistent and predictable outputs, you need to change how context is fetched and how the supervisor agent processes it.
## 1. Upgrade from Chunk RAG to Code Graphs
Instead of relying purely on vector embeddings of text chunks, extract and store structural metadata inside your metadata JSONB or a new mapping table.

* What to store: Classes defined, methods defined, and imported files.
* The Strategy: When the vector search finds a chunk in file_A.py, your system should automatically pull all files that file_A.py imports or depends on. This forces the supervisor to see the whole feature group.

## 2. Implement a Two-Pass Supervisor Flow
Do not ask the supervisor to generate the checklist and the affected files in a single, direct step. Break it into a deterministic chain:

[Plain Requirement] 
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│ Pass 1: Scope Identification Agent                      │
│ - Searches DB for system components.                     │
│ - Output: ONLY a strict list of Component/File Names.   │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│ Context Hydration Step                                  │
│ - Deterministically queries ALL database code blocks    │
│   belonging to the files identified in Pass 1.          │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│ Pass 2: Task Planner Agent                              │
│ - Receives 100% of the hydrated code text.             │
│ - Output: Final task_checklist and finalized files.     │
└─────────────────────────────────────────────────────────┘

## 3. Enforce Determinism in LLM Configurations
Ensure your supervisor agent's LLM parameters are locked down to prevent creative hallucinations:

* Set temperature = 0.0 (or as close to 0 as your framework allows).
* Use Structured Outputs (like JSON Schema or Pydantic) to force the model to output a strict schema.
* Implement a system prompt that explicitly tells the agent: "Do not guess files. Only list files explicitly provided in your context container." [3, 4, 5] 

------------------------------
To help you narrow down the exact issue, could you tell me a bit more about how you handle things on the code side? If you're open to sharing, I'd like to know:

* Which LLM model and framework (e.g., LangGraph, CrewAI, Autogen) are you using?
* How do you calculate your top-k retrieval limit when querying app_context_chunks?
* What does the system prompt for your supervisor agent look like?

I can help you adjust your retrieval queries or write a Pydantic schema to lock down the supervisor's choices.

[1] [https://pub.towardsai.net](https://pub.towardsai.net/multi-agent-systems-done-right-af91ac04edc4)
[2] [https://arxiv.org](https://arxiv.org/html/2607.16692v1)
[3] [https://kshitijkutumbe.medium.com](https://kshitijkutumbe.medium.com/detailed-guide-to-getting-structured-outputs-for-multi-agent-systems-4da7c0782146)
[4] [https://www.enkryptai.com](https://www.enkryptai.com/blog/why-agent-hooks-are-the-missing-layer)
[5] [https://www.sitepoint.com](https://www.sitepoint.com/multi-agent-ai-development-architecture/)
