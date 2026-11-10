# AGENTS.md

## Context

This is the starter repo for Assignment 1 of CMU 11-768 (AI Agents): build an agent harness. The full spec is in [ASSIGNMENT.md](ASSIGNMENT.md).

I am doing this assignment as a side project. I have not enrolled in the course. The grading, submission, quiz and `AI_USAGE.md` requirements in ASSIGNMENT.md do not apply to me. I still follow the spec so that my work passes the public tests and the `make check-*` targets.

## Setup

```bash
make setup    # uv sync + git submodule update --init + verify-sources
make doctor   # checks submodules, Modal auth and the model endpoint without billing
```

- Python is pinned to 3.14 in `.python-version`. `pyproject.toml` has no upper bound, and `modal==1.5.3` fails at import time on Python 3.15+, so don't remove the pin or raise it.
- Modal login: `uv run modal setup`.
- The Modal workspace's image builder version must be `2025.06` (dashboard: Settings → Image Config). New workspaces default to a newer version that `modal==1.5.3` rejects with a `VersionError`. Don't upgrade modal to work around this: in 1.6.x `Sandbox.terminate()` no longer waits, which breaks the cleanup checks in the Modal tests.

## Layout

- `src/assignment/agent/`: the code to implement. Look for `TODO(x.y)` markers that match the sections in ASSIGNMENT.md.
- `src/assignment/prompts.py`: prompt templates (may be changed).
- `tasks/`: task definitions, plus the skills that the *agent* loads at runtime (`tasks/code-skills`, `tasks/chess-skills`).
- `chess_app/`: git submodule containing the app the agent repairs. It must stay at the task's base commit, and `verify-sources` checks this.
- `tests/`: public tests. `scripts/`: evaluation scripts.

## Rules

- Do not modify `tests/`, `tasks/` or `chess_app/`.
- Leave code inside `### Do not modify this section ###` blocks unchanged (e.g. in `src/assignment/agent/base.py`).

## How to help me

- When an implementation depends on a public API or another transferable specification (e.g. the OpenAI tool-calling format, the Agent Skills protocol, YAML frontmatter, UCI/FEN), point me to the source first. Cite public sources (official docs, specs, API references) before source code such as the installed SDK in `.venv`; use source code as a secondary reference, or when no public doc covers the point. Name the specific page or file and what to look for in it. Don't give the answer directly unless I ask for it after reading.
- The TODO comments and ASSIGNMENT.md are often terse and assume background they don't explain. When a requirement is dense or ambiguous, first restate it in plain terms: what data is split or changed, where the result ends up, and why each constraint exists. Note where the real intent is only visible from a parameter name, a guard condition or a test, and cite that location.

## Testing and cost

- `make test`: fast, offline and free. Modal tests are excluded by default (`-m 'not modal'`).
- Billable (Modal credits and/or LLM tokens): `make test-modal`, `test-chess-modal`, `run-*`, `check-part1`, `check-swebench`, `run-chess-modal`. Ask before running any of these.
- After a crashed billable run, check `uv run modal container list` and stop any leftover sandbox with `uv run modal container stop <id>`. The `modal` CLI is only installed in `.venv`, so the bare `modal` command from ASSIGNMENT.md works only in an activated venv.
