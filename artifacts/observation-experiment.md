# Observation A/B experiment

Each run is one game as White against the server's deterministic depth-2 Black
bot, with step limit 200. The only difference between conditions is whether the
`<chess_state>` observation includes the `legal_moves` line (no-legal runs use
`--omit-legal-moves` and the matching system prompt). Board, FEN, status and
recent history are shown in both conditions.

Models: `deepseek/deepseek-v4-flash-0731` and `openai/gpt-oss-120b`.

## Results

| Model | Legal moves shown | `play_move` calls | Rejected as illegal | Invalid-move rate | `game_over: true` | Outcome |
|---|---|---|---|---|---|---|
| deepseek | no  | 65 | 2 | 3.1% | yes | White wins (Ra7#, 123 plies) |
| deepseek | yes | 41 | 0 | 0.0% | yes | Black wins (82 plies) |
| gpt-oss  | no  | 14 | 0 | 0.0% | yes | Black wins (28 plies) |
| gpt-oss  | yes | 30 | 1 | 3.3% | yes | Black wins (58 plies) |

Invalid-move rate = calls rejected as illegal / total `play_move` calls. The
deepseek no-legal run also had one call with truncated (malformed JSON)
arguments; it was returned as a `<chess_error>` and is not counted as illegal.

Supporting numbers from the trajectories:

| Model | Legal moves shown | Steps | Steps without a tool call | Prompt tokens | Completion tokens |
|---|---|---|---|---|---|
| deepseek | no  | 72 | 7  | 4,241,804 | 116,994 |
| deepseek | yes | 45 | 4  | 1,736,698 | 60,554 |
| gpt-oss  | no  | 26 | 12 | 94,568    | 33,085 |
| gpt-oss  | yes | 58 | 28 | 625,101   | 46,804 |

## Comparison

- **Legality.** Hiding legal moves did not measurably raise the invalid-move
  rate. All four runs were between 0% and 3.3%, with at most two rejections per
  game, and every rejection was recovered on the next call. With one game per
  condition this difference is noise. Both models can read a legal move off the
  board and FEN most of the time.
- **Game length and outcome.** The model mattered more than the observation.
  deepseek survived longer than gpt-oss in both conditions, and its no-legal
  game was the only win. One win against a weak bot is not evidence that
  omitting legal moves helps; gpt-oss's no-legal game was the shortest, ending
  after it gave away its queen (Qd5+ Kxd5).
- **Tool-call reliability.** About 45% of gpt-oss steps contained no tool call:
  it often wrote the move as JSON in its text (for example `{"move": "h8f7"}`)
  instead of calling `play_move`. deepseek's no-tool-call steps were rare (about
  10%) and were responses cut off at the completion-token limit. These steps do
  not count as invalid moves, but they cost steps and tokens.
- **Cost.** Without legal moves, the agent's reasoning has to reconstruct the
  position, and longer games compound this because there is no compaction. The
  deepseek no-legal run used about 2.4x the prompt tokens of its legal-moves run.

## Limitations

One game per condition, and games diverge after the first different move, so
the counts compare whole games rather than identical positions. A fair estimate
of the invalid-move rate would need several games per condition, or a fixed set
of positions replayed under both observations.

## Evidence

- `artifacts/part3-no-legal-moves-deepseek.json`, `artifacts/part3-no-legal-moves-deepseek-result.json`
- `artifacts/part3-legal-moves-deepseek.json`, `artifacts/part3-legal-moves-deepseek-result.json`
- `artifacts/part3-no-legal-moves-gpt-oss.json`, `artifacts/part3-no-legal-moves-gpt-oss-result.json`
- `artifacts/part3-legal-moves-gpt-oss.json`, `artifacts/part3-legal-moves-gpt-oss-result.json`
