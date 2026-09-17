# Combined Token-Efficiency Plan (Methods #1 + #2 + #8, weaknesses patched)

Goal: minimize tokensUsed WITHOUT increasing mistakes. Target ~1,800 tokens
(tokenBonus ~906) -> ~17,000 on the test map, full clear + 3 lives.

## Design principle
Move correctness OFF the model (unreliable, high-variance) and INTO the
Lambda tools (deterministic). The model's job shrinks to: pick the tool, then
echo its result verbatim. Fewer model decisions = fewer tokens AND fewer
mistakes simultaneously.

## The three methods, layered

### Layer A — Output discipline (#2), patched against Thinking-loss
- Ban preambles, narration, retries, double tool calls (targets the 3,835-token
  bloat: "Let me correct...", "Retrying...", "Based on the previous...").
- PATCH for the Thinking-channel weakness: instead of "emit ZERO reasoning"
  (which pushed answers into Thinking), say "COMMIT your reply as the visible
  final answer." A committed-answer instruction, not a reasoning-ban.

### Layer B — Structured, tool-provided outputs (#8), patched against wrong-format
- For c3: the Lambda returns the COMPLETE "Scanning the map" string in `result`;
  the model echoes `result` verbatim. (Already done in merged Pathfinding.)
- For c4: the Lambda returns page content; prompt requires verbatim quote + value
  (anti-hallucination). Keep this format — do NOT compress it.
- For c18: fixed one-line JSON template. Keep exact.
- PATCH for wrong-format: the format is DEFINED BY THE TOOL OUTPUT, not invented
  by the model. Model just copies. Removes the "bare 2" failure class.

### Layer C — Prompt compression (#1), patched against dropped-challenge
- Keep the MATCH-IN-ORDER routing table (1..9) — this is the anti-drop guard.
- Compress WORDING (shorter sentences) but NEVER remove a challenge's rule.
- PATCH for dropped-challenge: every challenge id (c1-c5, c18, c30/31, c40/41,
  c17) must retain an explicit line. Verified by the reliability router test.

## Weakness-patch matrix
| Method | Weakness (from our logs) | Patched by |
|--------|--------------------------|------------|
| #1 compress prompt | ultralean dropped a challenge | #8 explicit per-challenge format lines + routing table kept |
| #2 output limit | Martinez/lisinopril c1 -> Thinking/no-capture LOSS | reframe as "commit as final answer" (not "no reasoning") |
| #8 rigid format | c3 bare "2" -> LoseChallenge | tool returns full formatted `result`; model echoes verbatim |

## Token budget per challenge (target)
- path: ~350 tok (the move array — unavoidable, biggest single item)
- c3: ~30 tok (echo result)
- c4 x2: ~25 tok each (quote+value)
- c2 x2: ~15 tok each (tool + number)
- c5 x4: ~3 tok each
- c1 x4: ~11 tok each (fixed refusal)
- c18: ~35 tok
- keys x2: ~2 tok each (Thanks)
- doors x2: ~10 tok each (tool result)
Sum ~ 650 answer tokens + framework overhead. Real runs that hit ~1,800 total
prove this budget is achievable when preambles are suppressed.

## What NOT to do (proven mistakes)
- Do NOT go ultralean (drops challenges).
- Do NOT compress c4 quote (reintroduces hallucination).
- Do NOT use "ZERO reasoning" phrasing (causes Thinking-channel loss).
- Do NOT call any tool twice (c4 double-call bloat).
