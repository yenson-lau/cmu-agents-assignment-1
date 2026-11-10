# Token usage: compaction vs. full context

Task: `django__django-15368` (`bulk_update()` ignores plain `F()` expressions), model `deepseek/deepseek-v4-flash-0731`, step limit 200. Token counts are the provider-reported `usage` of every API call, including the compaction calls. Each setting was run once, so the numbers are indicative rather than statistically reliable.

| | Threshold 0 (no compaction) | Threshold 6000 | Threshold 1 (compact every step) |
|---|---|---|---|
| Trajectory | `django__django-15368-baseline-trajectory.json` | `django__django-15368-trajectory.json` | `django__django-15368-t1-trajectory.json` |
| Outcome | Submitted a patch (not graded) | `check-swebench`: RESOLVED | Sandbox disconnected at step 104, no patch |
| Steps | 36 | 25 | 104 |
| Compactions | 0 | 9 | 102 |
| Agent prompt tokens, total | 809,765 | 106,560 | 295,708 |
| Prompt size: max / mean / final | 39,160 / 22,493 / 39,160 | 6,174 / 4,262 / 3,363 | 5,136 / 2,843 / 3,060 |
| Agent completion tokens | 9,099 | 5,256 | 13,410 |
| Compaction tokens (prompt + completion) | 0 | 47,148 | 257,026 |
| **Total tokens** | **818,864** | **158,964** | **566,144** |
| Share spent on compaction | 0% | 30% | 45% |
| Cached prompt tokens | 600,576 (74%) | 57,088 (54%) | 133,632 (45%) |
| Reported cost | $0.0487 | $0.0133 | $0.0677 |

## Observations

**Without compaction, the prompt grows every step.** Each request resends the whole history, so the prompt rises from 1.7k to 39k tokens, and the total grows roughly with the square of the number of steps. The cost is also spread unevenly: the last steps cost about 20× as much as the first ones.

**With a 6,000-token threshold, the prompt stays bounded.** Prompt size moves in a sawtooth between about 2.7k and 6.2k tokens, so the total grows roughly linearly. The difference is not just because this run took fewer steps: over its first 25 steps alone, the baseline sent 429k prompt tokens, 4× the compacted run's whole total. Overall, the compacted run used 5.2× fewer tokens and cost 3.7× less.

**Compaction has its own cost.** The 9 summary calls used 47k tokens, 30% of the run. Compactions also bunched up early (steps 5–9, every step), because the retained step held a large tool output: after summarizing, the prompt was still close to the threshold and went over again on the next step. When the size left after compaction sits close to the threshold, the agent compacts on nearly every step.

**Prompt caching narrows the cost gap.** In the baseline, the prompt only grows at the end, so 74% of its prompt tokens were cache hits. Each compaction rewrites the history and breaks the cached prefix. That is why the cost ratio (3.7×) is smaller than the token ratio (5.2×).

**Compacting too much costs more and makes the agent fail.** At threshold 1, the agent kept only its latest step plus a summary. Its prompts were the smallest of the three, yet it used 3.6× the tokens of the 6,000 run and cost more than the full-context baseline. The fix was applied and tested early, but the agent then looped through submission: it invoked `submit-task` 9 times, wrote `patch.txt`, deleted it, and re-ran tests until the sandbox disconnected. The submission procedure arrives as a tool result, and a summary that paraphrases tool output loses it. The summaries also recorded what the agent had done, but not which step of the process it was on.

**How the compaction prompt is built matters.** An earlier version passed the old history as real `assistant`/`tool` messages (`django__django-15368-structured-*`). At step 26, the model continued the task ("I'll create the patch file now…") instead of summarizing, which erased steps 1–25. Serializing the history to JSON inside a single user message removed that failure: all 9 summaries in the 6,000 run were real summaries.

## Tradeoffs

- **Full context** keeps every detail, needs no extra calls and benefits most from caching. But the prompt grows every step, the total grows roughly with the square of the step count, and a long enough task will exceed the context window.
- **Compaction** keeps each request small and bounded, and the total grows about linearly. The costs are extra summary calls, a shorter cached prefix, and the risk that a summary drops something important. That risk is highest for exact text such as skill instructions.
- **The threshold controls the trade-off.** A threshold that is too low spends the budget on summaries and erases the context the agent needs to act. Here, 6,000 tokens was the cheapest setting and the only one confirmed to solve the task.
