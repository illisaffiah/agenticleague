# agenticleague — AWS AI League Dungeon Game Agent

An agentic solution for the **AWS AI League** dungeon game. A supervisor LLM navigates a
grid maze to the treasure, solving a variety of challenges along the way. Each challenge
type is delegated to a purpose-built **AgentCore Gateway tool** (a Lambda function), and a
terse, rule-ordered **supervisor prompt** routes each challenge to the right tool while
minimizing token spend.

> **Rules note:** answers are **never hardcoded**. Every answer is derived at runtime through
> general logic (counting tiles, transforming keys, evaluating math, reading fetched web
> content). The same configuration is intended to generalize to the hidden judge map.

---

## Scoring model

The final score is the sum of:

| Component            | How it is earned                                                     |
|----------------------|----------------------------------------------------------------------|
| **Coins**            | 250 per coin tile collected (14,350 for a full 28-coin clear)        |
| **Life bonus**       | 250 × lives remaining                                                |
| **Treasure bonus**   | 1,000 for reaching the treasure                                      |
| **Token bonus**      | `1000 − round(tokensUsed / challengesAttempted)`                     |
| **Custom-model bonus** | Awarded only when a fine-tuned custom model is used                |

**Proven ceiling on the fixed practice map: ~17,003** (full clear, 3 lives, ~1,844 tokens).
The remaining upside (~17,600) depends on a lucky real-map draw with **0 forced spikes → 5 lives**,
which the pathfinder is built to fully clear when it appears.

---

## Repository structure

```
agenticleague/
├── README.md                         # this file
├── lambdas/                          # the 5 deployed AgentCore Gateway tools
│   ├── mapanalyzer_lambda.py         # pathfinding + tile counting (pocket-value solver)
│   ├── mathevaluation_lambda.py      # hardened safe math interpreter (c2)
│   ├── websearch_lambda.py           # URL fetch + content extraction (c4)
│   ├── cipher_lambda.py              # green-key letter→number transform (c31 door)
│   └── redladder_lambda.py           # red-key transform (c30 door)
├── prompts/
│   └── supervisor_prompt.md          # the live, terse orchestrator prompt
├── config/
│   └── guardrail_settings.md         # Bedrock guardrail topics + filter config
├── tests/                            # verification harnesses (run from repo root)
│   ├── mapanalyzer_nonregression_test.py
│   ├── failproof_test.py
│   ├── failproof_test2.py
│   ├── pocket_fix_comparison.py
│   ├── prompt_reliability_test.py
│   └── prompt_adversarial_test.py
├── pathfinding-dataset/              # RLVR dataset for optional pathfinder fine-tuning
├── docs/
│   └── token_efficiency_plan.md      # token-reduction analysis and plan
└── experiments/                      # archived, non-deployed explorations
    ├── probes/                       # map/move-format/token probes and simulators
    ├── alt-prompts/                  # earlier supervisor-prompt variants + guardrail experiment
    └── prototypes/                   # merged-tool / TSP / original-Lambda prototypes
```

---

## The five deployed tools (`lambdas/`)

All tools accept the AgentCore Gateway invocation shape
(`{"parameters":[{"name","value"}, ...]}`) as well as direct test payloads, and return
`{"result": ...}`.

### `mapanalyzer_lambda.py` — pathfinder & tile counter
Handles two challenge families:
- **Pathfinding** (`Find … treasure`): returns a full-word move array
  (`["right","right","down", …]`) that visits every collectible while respecting walls,
  keys/doors ordering, and spike costs.
- **Tile counting** (c3 *"How many `<tile>` … on the map"*): returns the matched positions
  and the count.

**Pocket-value spike decision:** the solver crosses a spike **only if the total reward of the
pocket it unlocks strictly exceeds the life cost** (strict `>`, so ties keep the life). This
maximizes score on both the fixed map (crossing the 2 forced cut-vertex spikes A6/F7 to reach
3,750 pts of content is optimal → still 3 lives) and on randomized draws with *optional*
spike-pockets (skip low-value pockets, keep the life bonus).

### `mathevaluation_lambda.py` — hardened safe math interpreter
Evaluates small code snippets for c2 (factorial/Fibonacci modulo). Hardened to reliably parse
the model's variety of outputs:
- accepts augmented assignment (`r *= i`), `while` loops, and a broader builtin set;
- recognizes alternate result variable names (`result`, `answer`, `ans`, `res`, `r`);
- robust multi-shape input extraction.
These changes address intermittent c2 losses when the model phrased the computation differently.

### `websearch_lambda.py` — URL fetch (c4)
Fetches the page named in *"According to `<url>` …"* and returns its text so the supervisor can
quote the answer **verbatim from the fetched content** rather than from memory.

### `cipher_lambda.py` — green-key transform (c31 door)
Applies the green-key `letter_to_number` transform to whatever key value was received.

### `redladder_lambda.py` — red-key transform (c30 door)
Applies the red-key transform to the received key value. Kept as a **separate tool** from the
cipher on purpose — reliability over tidiness; merging them reintroduced a door-answer decision
that previously caused a wrong-answer death.

---

## Supervisor prompt (`prompts/supervisor_prompt.md`)

A single terse orchestrator prompt. Key design points:
- **Token discipline:** zero preamble, no narration, one committed answer or one tool call per
  challenge, at most one tool call per challenge.
- **First-match rule ordering:** structured challenges always win over the guardrail; the c1
  guardrail refusal is the last resort.
- **c3 terseness exception:** c3 requires the full multi-line `Scanning the map:` block — a bare
  number is rejected by the game.
- **c4 URL-only rule:** call the fetch tool once with the URL only (no keywords) to avoid a
  double-call token blow-up, and quote the returned sentence verbatim.
- **Key/door protocol:** a *"Key N is: V"* statement is acknowledged with only `Thanks` (value is
  silently remembered); the matching door later routes to the cipher/redladder transform.

---

## Guardrail (`config/guardrail_settings.md`)

Bedrock guardrail with denied topics (Medical advice, Harmful content, Privacy violation, Hate
speech, Financial advice) and content filters. Blocked prompts/responses return exactly:

> `Sorry, the model cannot answer this question.`

A catch-all topic was tested and **reverted** — it caused a net score loss without fixing the
underlying (timing-related) refusal edge case.

---

## Tests

Run from the repository root:

```bash
python3 tests/mapanalyzer_nonregression_test.py
```

The non-regression test replays the fixed practice map through the deployed pathfinder and
asserts a full clear:

```
coins:      28/28 OK
challenges: 14/14 OK
keys:       2/2 OK
doors:      2/2 OK
DISTINCT spike tiles hit (= lives lost): 2 ['A6', 'F7']  (forced minimum) OK
lives remaining: 3   lifeBonus preserved: YES (750)
```

Other harnesses: `failproof_test*.py` (Lambda robustness), `pocket_fix_comparison.py`
(head-to-head score comparison of the pocket-value decision), and the prompt
reliability/adversarial tests.

---

## Deploying a tool

Tools are deployed to Lambda functions named `AgentCoreGatewayTool-<name>-<suffix>` with handler
`lambda_function.lambda_handler`. General pattern (back up first, validate, then update):

```bash
# from the tool's deploy directory
cp lambda_function.py lambda_function.BACKUP_$(date +%s).py           # 1. back up current
cp /path/to/agenticleague/lambdas/<tool>.py lambda_function.py        # 2. swap in new code
python3 -c "import ast; ast.parse(open('lambda_function.py').read())" # 3. validate syntax
python3 -c "import zipfile; zipfile.ZipFile('function.zip','w').write('lambda_function.py')"
aws lambda update-function-code \
  --function-name AgentCoreGatewayTool-<name>-<suffix> \
  --zip-file fileb://function.zip --region us-east-1                  # 4. deploy
```

Always keep the previous known-good zip so you can roll back if a run regresses.

---

## Changelog — what this reorganization changed

This branch reorganizes a previously flat, experiment-heavy layout into a clear structure that
separates **deployed code** from **experiments**, and promotes the latest working versions of
each component into canonical locations.

**Structure**
- Introduced `lambdas/`, `prompts/`, `config/`, `tests/`, `docs/`, and `experiments/`.
- Removed the legacy duplicate `working v2/` and `working version/` directories (superseded by
  the organized `lambdas/`, `prompts/`, and `config/`).

**Promoted latest working code**
- `mapanalyzer_lambda.py` → `lambdas/` — the **pocket-value** pathfinder (crosses a spike only
  when the unlocked pocket's reward strictly exceeds the life cost). Verified: full clear, 3
  lives on the fixed map.
- `mathevaluation_lambda_hardened.py` → `lambdas/mathevaluation_lambda.py` — the **hardened**
  interpreter becomes the canonical math tool; the earlier version is archived under
  `experiments/prototypes/mathevaluation_lambda_original.py`.
- `cipher_lambda.py` and `redladder_lambda.py` added to `lambdas/` (previously they lived only
  outside the repo), so all five deployed tools are now version-controlled together.
- `supervisor_prompt_terse_reverted.md` → `prompts/supervisor_prompt.md` — the live terse prompt
  (c3 terseness exception + c4 URL-only rule) becomes canonical; earlier variants archived under
  `experiments/alt-prompts/`.

**Tests & docs**
- Test harnesses moved under `tests/`; the non-regression test's import was updated to locate the
  Lambda under `lambdas/`, and it **still passes** (3 lives / full clear) from the repo root.
- `token_efficiency_combined_plan.md` → `docs/token_efficiency_plan.md`.

**Archived (not deleted)**
- All probes, simulators, alternate prompts, and merged/TSP prototypes moved under `experiments/`
  for reference without cluttering the deployed surface.

**Preserved**
- `pathfinding-dataset/` (RLVR training/validation data) kept as-is for optional fine-tuning.
