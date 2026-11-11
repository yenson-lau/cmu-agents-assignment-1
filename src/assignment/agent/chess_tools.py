"""Chess tool implementations, decoupled from the agent that registers them.

Every function here takes the HTTP client explicitly instead of reading it off
an agent, so the same code can run in the agent process or inside the sandbox
beside the server it talks to.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

CHESS_PORT = 8000


def _request_state(
    client: httpx.Client, method: str, endpoint: str, **kwargs: Any
) -> dict[str, Any]:
    """Make one chess API request and validate its JSON response."""

    response = client.request(method, endpoint, **kwargs)
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Chess server returned non-JSON ({response.status_code})."
        ) from exc
    if response.status_code >= 400:
        detail = (
            payload.get("detail", payload) if isinstance(payload, dict) else payload
        )
        raise ValueError(str(detail))
    if not isinstance(payload, dict):
        raise RuntimeError("Chess server response must be a JSON object.")
    return payload


def _simulate_move(client: httpx.Client, arguments: str) -> str:
    """New tool: inspect FEN or simulate one ply without changing the game.

    Takes the raw JSON arguments of one tool call and returns the observation
    to send back, so a bad argument or a server error reaches the model as a
    recoverable ``<chess_error>`` instead of ending the run.
    """
    # (Part 3.3.b): Parse the arguments, call the provided
    # /api/simulate endpoint with fen and optional move, and return its JSON.
    # Catch any errors raised by the tool and return an error message between
    # `<chess_error></chess_error>` for the agent to address. Cover malformed
    # JSON arguments, arguments that are not an object, a missing or
    # non-string fen, a non-string move, a position or move the server rejects,
    # and a transport failure.

    # Parsing
    try:
        parsed = json.loads(arguments)
    except (json.JSONDecodeError, TypeError) as exc:
        return _chess_error_message(f"Malformed JSON arguments: {exc}")

    if not isinstance(parsed, dict):
        return _chess_error_message("Arguments must be a JSON object.")

    if not isinstance(fen := parsed.get("fen"), str):
        return _chess_error_message("Arguments must contain `fen` (str).")

    if not (isinstance(move := parsed.get("move", False), str) or (move is None)):
        return _chess_error_message("Arguments must contain `move` (str | null).")

    if len(parsed) > 2:
        return _chess_error_message(
            "Arguments must consist only of `fen` and `move` values."
        )

    # Request
    try:
        payload = _request_state(
            client,
            method="POST",
            endpoint="/api/simulate",
            json={"fen": fen, "move": move},
        )
    except ValueError as exc:
        # The server rejects the FEN or move: illegal (400) or failed validation (422).
        return _chess_error_message(f"Simulation rejected: {exc}")
    except RuntimeError as exc:
        # The server answered, but not with a JSON object.
        return _chess_error_message(str(exc))
    except httpx.HTTPError as exc:
        return _chess_error_message(f"Could not reach the chess server: {exc}")

    return json.dumps(payload)


def _chess_error_message(message: str) -> str:
    return f"<chess_error>{message}</chess_error>"


def _play_move(client: httpx.Client, arguments: str) -> str:
    """Existing tool: play one move as White and return the resulting state.

    Takes the raw JSON arguments of one tool call. Returns the new state, or a
    `<chess_error>` observation if the move could not be played.
    """
    # (3.1.b): Parse the arguments and POST {"move": <uci move>} to
    # /api/move. Return its JSON object. Catch any errors raised by the
    # tool and return an error message between `<chess_error></chess_error>`
    # for the agent to address. Cover malformed JSON arguments, arguments
    # that are not an object, a non-string move, a position or move the server
    # rejects, and a transport failure.

    # Parsing
    try:
        parsed = json.loads(arguments)
    except (json.JSONDecodeError, TypeError) as exc:
        return _chess_error_message(f"Malformed JSON arguments: {exc}")

    if not isinstance(parsed, dict):
        return _chess_error_message("Arguments must be a JSON object.")

    if not isinstance(move := parsed.get("move"), str):
        return _chess_error_message("Arguments must contain a UCI string `move`.")

    if len(parsed) > 1:
        return _chess_error_message("Arguments must contain a single `move` value.")

    # Request
    try:
        payload = _request_state(
            client,
            method="POST",
            endpoint="/api/move",
            json={"move": move},
        )
    except ValueError as exc:
        # The server rejected the move: illegal (400) or failed validation (422).
        return _chess_error_message(f"Move rejected: {exc}")
    except RuntimeError as exc:
        # The server answered, but not with a JSON object.
        return _chess_error_message(str(exc))
    except httpx.HTTPError as exc:
        return _chess_error_message(f"Could not reach the chess server: {exc}")

    return json.dumps(payload)


def _run_python(env: Any, port: int, arguments: str) -> str:
    """New tool: run Python with access to the existing registered tools.

    The snippet runs inside the sandbox, which already has the tool
    implementations and the chess server, so code the model wrote never
    executes in the agent process.
    """
    # TODO(3.4): parse the arguments and run the code in the
    # sandbox with the registered tools available by name.
    #
    # `/opt/assignment/sandbox_python.py` is a script on the `env` sandbox
    # that has access to the same tool definitions in this file. Use it to run
    # the code that the model produced as an argument to the run_python tool.
    # The script accepts two positional arguments -- `port` and a base64-encoded
    # string of code (to prevent issues with quoting). Implement this tool
    # call.
    #
    # The script prints one JSON object with `stdout`, `stderr`, and `error`
    # from running the code -- return that string as it is.
    #
    # A non-zero returncode means the sandbox itself failed, not the model's
    # code. Report `exception_info` or `stderr` as a <chess_error>.
    #
    # Return <chess_error>{message}</chess_error> if there are issues like type
    # mismatches or parsing failures.
    raise NotImplementedError


def _invoke_skill(skills: dict[str, dict[str, str]], arguments: str) -> str:
    """Existing tool: load one skill's instructions into the conversation."""
    # TODO(3.5): parse the arguments and return the named skill's content.
    # Return <chess_error>{message}</chess_error> if there are issues like type
    # mismatches or parsing failures.
    raise NotImplementedError


def _game_state(client: httpx.Client, reset: bool = False) -> dict:
    """Read the live game, or start a new one and read the opening position."""

    method, endpoint = ("POST", "/api/reset") if reset else ("GET", "/api/state")
    return _request_state(client, method, endpoint)
