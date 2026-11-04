"""The Part 1 coding agent: fix a software issue and submit a git patch."""

from __future__ import annotations

import json
from textwrap import dedent
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from assignment.agent.base import (
    DEFAULT_COMPACTION_KEEP_RECENT_STEPS,
    DEFAULT_COMPACTION_MAX_TOKENS,
    Agent,
    format_tool_output,
)
from assignment.agent.tools import EXECUTE_TOOL, SEND_MESSAGE_TOOL
from assignment.env import Environment


CommandArg = (
    Annotated[str, Field(min_length=1)] |
    Annotated[list[str], Field(min_length=1)]
)


class ExecuteArgs(BaseModel):
    """Arguments of the `execute` tool, mirroring `EXECUTE_TOOL`'s schema."""

    model_config = ConfigDict(extra="forbid")

    command: CommandArg
    shell: bool | None = None
    cwd: str | None = None
    timeout: float | None = None
    env: dict[str, str] | None = None


class SendMessageArgs(BaseModel):
    """Arguments of the `send_message` tool, mirroring `SEND_MESSAGE_TOOL`'s schema."""

    model_config = ConfigDict(extra="forbid")

    summary: str


class InvokeSkillArgs(BaseModel):
    """Arguments of the `invoke_skill` tool, mirroring `INVOKE_SKILL_TOOL`'s schema."""

    model_config = ConfigDict(extra="forbid")

    name: str


class CodeAgent(Agent):
    """An agent that fixes a software issue and submits a git patch."""

    def __init__(
        self,
        task: str,
        environment: Environment,
        model: str | None = None,
        logs_save_path: str | None = None,
        step_limit: int = 100,
        skills_path: str | None = None,
        auto_stop_environment: bool = True,
        compact_threshold_tokens: int | None = None,
        compaction_keep_recent_steps: int = DEFAULT_COMPACTION_KEEP_RECENT_STEPS,
        compaction_max_tokens: int = DEFAULT_COMPACTION_MAX_TOKENS,
    ):
        super().__init__(
            environment=environment,
            model=model,
            logs_save_path=logs_save_path,
            step_limit=step_limit,
            skills_path=skills_path,
            auto_stop_environment=auto_stop_environment,
            compact_threshold_tokens=compact_threshold_tokens,
            compaction_keep_recent_steps=compaction_keep_recent_steps,
            compaction_max_tokens=compaction_max_tokens,
        )
        self.task = task
        self.submitted_patch = ""

        # (1.3): Make the `execute` and `send_message` tools available
        # to the agent.

        self.tools += [EXECUTE_TOOL, SEND_MESSAGE_TOOL]

        # (1.1.b): Construct the system prompt and task_prompt. These
        # should be usable by the `Agent.build_prompt` method.
        #
        # NOTE: A strong system prompt for this assignment is around 10–15
        # lines: role and /testbed, the workflow, "one tool call per step, read
        # output first," "keep working until verified, then call send_message,"
        # and the system-info block.

        system_info = {
            "machine": environment.machine,
            "release": environment.release,
            "system": environment.system,
            "version": environment.version,
        }

        self.system_prompt = dedent("""
            You are a coding agent operating within a repository in the following code sandbox:

            <system_information>
            {system_info}
            </system_information>

            The repository is a git repo with a single base commit checked out at `/testbed`, your working directory.

            Solve the task provided by the user by repeatedly working and making tool calls until you can verify the fix. Once you are done, call the `send_message` tool to submit a summary of your work.

            Some tips:
            - General workflow: Explore the relevant code, reproduce the failure, make the fix, then rerun the reproduction and existing tests to confirm the fix.
            - Note that no one will answer questions; act autonomously and keep using tools until the task is done.
            - Avoid interactive or never-ending commands (editors, pagers, servers in the foreground), and edit files with shell tools such as `sed`, `cat <<'EOF'` or `python -c`.
            - Use `git status` / `git diff` to review your changes
        """).strip().format(system_info=json.dumps(system_info, indent=2))

        # (1.4): If any skills are available to the agent, make their
        # descriptions/metadata available to the agent in the prompt.

        if (skills := self.skills):
            skill_catalog = "\n\n".join(
                f"<skill>\n{skill['metadata']}\n</skill>"
                for skill in skills.values()
            )

            self.system_prompt += "\n\n" + dedent("""
                You should also consult the following skills whenever necessary, by calling the `invoke_skill` tool:

                <available_skills>
                {skills_catalog}
                </available_skills>
            """).strip().format(skills_catalog=skill_catalog)

        self.task_prompt = task

    def _env_execute(self, args: Any) -> str:
        parsed = ExecuteArgs.model_validate(args)
        # Omitted optional arguments keep `Environment.execute`'s own defaults.
        result = self.env.execute(**parsed.model_dump(exclude_none=True))
        return f"`execute` call result: {format_tool_output(result)}"

    def _send_message(self, args: Any) -> str:
        parsed = SendMessageArgs.model_validate(args)
        self.finished = True
        return f"Loop finished. Summary: {parsed.summary}"

    # (1.4) cont.: Add the `invoke_skill` tool to the agent. All it does is send the content to the agent as a tool result.
    def _invoke_skill(self, args: Any) -> str:
        parsed = InvokeSkillArgs.model_validate(args)
        name = parsed.name

        if not (skill := self.skills.get(name)):
            return (
                f"Unknown skill '{name}'."
                f" Available skills: {list(self.skills.keys())}"
            )

        skill_content = dedent("""
            Content of skill {name} returned by `invoke_skill`:

            <skill_content>
            {content}
            </skill_content>
        """).strip().format(name=name, content=skill["content"])

        return skill_content

    def execute_tool_calls(
        self, tool_calls: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        """Execute ``execute`` and ``send_message`` calls in the code sandbox."""

        # (1.3): Parse each call, execute recognized tools, and return
        # one message per call (there may be multiple tool calls in one agent
        # response!). Malformed JSON and unknown tools must become recoverable
        # observations relayed to the agent instead of exceptions.

        messages = []

        def _add_message(_id: str, text: str):
            messages.append({"role": "tool", "tool_call_id": _id, "content": text})

        for tool_call in tool_calls:
            # potential malformed responses
            _id = "unknown"
            try:
                _id = tool_call["id"]
                assert tool_call["type"] == "function"
                function = tool_call["function"]
                tool_name = function["name"]
                arguments = function.get("arguments")
            except (KeyError, TypeError, AssertionError):
                _add_message(_id, f"Malformed tool call: {tool_call}")
                continue

            # assert tool is recognized
            if tool_name not in self.tool_names:
                _add_message(_id, f"Unknown tool: {tool_name}")
                continue

            # parse arguments
            try:
                parsed_args = json.loads(arguments)
            except (TypeError, json.JSONDecodeError):
                _add_message(_id, f"Malformed arguments: {arguments}")
                continue

            # execute tool; invalid arguments (wrong shape, types, or extra
            # fields) are reported back for the model to correct
            handler = {
                "execute": self._env_execute,
                "send_message": self._send_message,
                "invoke_skill": self._invoke_skill,
            }[tool_name]
            try:
                result = handler(parsed_args)
            except ValidationError as exc:
                result = f"Invalid arguments for `{tool_name}`: {exc}"
            _add_message(_id, result)

        return messages
