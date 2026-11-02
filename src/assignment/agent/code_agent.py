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

        # TODO(1.1.b): Construct the system prompt and task_prompt. These
        # should be usable by the `Agent.build_prompt` method.
        self.system_prompt = ""

        self.task_prompt = ""

        # FOLLOW UP: A strong system prompt for this assignment is around 10–15
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
            <system_information>
            {system_info}
            </system_information>
        """).format(system_info=json.dumps(system_info, indent=2))

        self.task_prompt = task

        # TODO(1.4): If any skills are available to the agent, make their
        # descriptions/metadata available to the agent in the prompt.

    def _env_execute(self, args: Any) -> str:
        parsed = ExecuteArgs.model_validate(args)
        # Omitted optional arguments keep `Environment.execute`'s own defaults.
        result = self.env.execute(**parsed.model_dump(exclude_none=True))
        return f"`execute` call result: {format_tool_output(result)}"

    def _send_message(self, args: Any) -> str:
        parsed = SendMessageArgs.model_validate(args)
        self.finished = True
        return f"Loop finished. Summary: {parsed.summary}"

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
            }[tool_name]
            try:
                result = handler(parsed_args)
            except ValidationError as exc:
                result = f"Invalid arguments for `{tool_name}`: {exc}"
            _add_message(_id, result)

        return messages
