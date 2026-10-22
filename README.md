# Code Orchestrator Agent

Code Orchestrator Agent is a multi-agent software engineering workflow concept for turning a development objective into traceable implementation tasks. It combines repository context, task planning, specialized agent handoffs, implementation, and review in a cyclic agentic loop.

The central idea is to give each implementation task a bounded and relevant slice of code context instead of passing the entire repository to every agent.

## Goals

- Ground tasks in repository structure and code dependencies.
- Break a larger request into an ordered checklist of smaller tasks.
- Give each task explicit target files, context, and technical constraints.
- Separate architecture, implementation, and review responsibilities.
- Use review feedback to drive bounded corrective iterations.
- Preserve task-level traceability throughout the workflow.

## Workflow

1. **Workflow intake** — Receive a feature request, bug report, or engineering objective.
2. **Repository context** — Inspect the codebase and use a code graph or dependency relationships to identify relevant files and execution paths.
3. **Task planning** — Generate a checklist, including dependencies and completion criteria.
4. **Architect handoff** — For each task, define target files, sliced code context, technical specifications, and expected behavior.
5. **Coder handoff** — Implement the task using the supplied context and constraints.
6. **Validation** — Run the configured compilation, tests, or other validation checks.
7. **Reviewer feedback** — Evaluate the change against requirements and validation results, then produce actionable feedback.
8. **Iteration or completion** — Route failed or incomplete work back through the loop; mark the task complete when its acceptance criteria are met.

## Agent responsibilities

| Component | Responsibility |
|---|---|
| Orchestrator | Maintains workflow state, task ordering, and agent handoffs |
| Context / code-graph stage | Finds relevant files and dependency paths |
| Planner | Creates the task checklist and task dependencies |
| Architect | Defines target files, sliced context, and technical specifications |
| Coder | Implements one task at a time |
| Reviewer | Checks requirements, code quality, and validation feedback |
| Validator | Runs configured build, compilation, and test commands |

These roles describe the intended separation of responsibilities. A concrete implementation may combine or split them depending on the framework.

## Cyclic agentic loop

The workflow is iterative rather than a one-way chain. Reviewer feedback can return a task to the coder, and task completion can unlock dependent tasks. This pattern is often described as an agentic loop or cyclic workflow. The code graph and task dependency graph serve different purposes: one represents relationships in the repository, while the other represents execution order and dependencies between planned tasks.

## Design principles

- **Context slicing:** Supply only the code and specifications relevant to the current task.
- **Explicit acceptance criteria:** Make expected behavior and completion checks visible.
- **Bounded retries:** Avoid endless correction loops by setting retry and escalation limits.
- **Validation over assertion:** Treat actual build/test results as stronger evidence than an agent's claim that code is correct.
- **Traceability:** Keep task status, changed files, validation results, and review feedback associated with each task.
- **Human oversight:** Require a developer to review consequential changes, security-sensitive work, and ambiguous requirements.

## Technology

The exact framework depends on the implementation. The architectural concepts include:

- Large Language Models (LLMs)
- Multi-agent orchestration
- Code-graph and dependency analysis
- AST or repository indexing, where available
- Task checklists and workflow state
- Agent-to-agent (A2A) handoffs
- Build, compilation, and automated test integration
- Structured review feedback

Replace this section with the exact libraries, models, and runtime used by your repository.

## Example task record

A task can be represented conceptually with:

```yaml
id: implement-session-timeout
objective: Enforce session expiration
target_files:
  - src/auth/session-service.ts
context:
  - session creation and validation paths
specification:
  - reject expired sessions
  - preserve existing refresh behavior
acceptance_criteria:
  - unit tests cover expired and active sessions
status: planned
```

This is an illustrative record, not a claim about the repository's exact schema.

## Validation strategy

A robust implementation should configure and record:

- Formatting and lint checks
- Type checking or compilation
- Relevant unit and integration tests
- Regression tests for changed behavior
- Security checks for sensitive code paths
- Reviewer findings and unresolved issues

A successful compilation alone does not prove that the implementation meets product requirements.

## Potential improvements

- Incremental code-graph indexing and change-aware context retrieval
- Explicit task dependency scheduling
- Token/context budgets for each agent
- Structured tool calls and schema validation
- Retry limits, timeouts, and failure recovery
- Human approval gates for risky changes
- Diff-aware review and test selection
- Workflow visualization and audit logs

## Project status

This README documents the architecture and intended workflow. Update it with the actual orchestration framework, supported tools, environment variables, commands, and validation results before presenting the project as production-ready.
