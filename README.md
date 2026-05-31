# Quorum

**A panel of specialist agents that reviews a Claude Code plan before a human approves it — and gives the human *less* to read.**

When a coding agent emits a plan, people skim it, fatigue, and rubber-stamp — missing scope creep, risky operations, and contradictions with what was actually asked for. Quorum runs a panel of narrow specialist reviewers over the plan, then an arbiter reconciles their findings into a short, triaged decision queue: only the few things that genuinely need a human, with everything else auto-cleared.

> Built for the Multi-Agent Orchestration Build Day (hackathon). Solo build, Python.

---

## The idea in one picture

```
                    ┌─→ Risk agent ────────┐
inputs/plan.md ─────┼─→ EdgeCase agent ────┼─→ Arbiter ──→ Decision queue
inputs/expectations/┴─→ Expectation agent ─┘   (reconciles)   (short markdown)
   (Expectation only)
```

- **3 specialists run in parallel**, each with one narrow job (and explicit exclusions so they don't overlap).
- **The arbiter is the only agent that sees everything.** It cross-references the findings against each other and against the docs, then decides per finding: **suppress / keep / escalate**.
- The output is a **triaged queue**, not a document. Most findings auto-clear; only the contested ones surface.

The reconciliation is the "why multi-agent": e.g. Risk flags a `DROP TABLE` as dangerous, but the meeting notes authorized it → the arbiter **suppresses** it. Identical operation elsewhere with no authorization → **escalate**. No single agent can make that call.

---

## The agents

| Agent | Job (and *only* this) | Model | Input |
|---|---|---|---|
| **Risk** | Destructive / irreversible operations (drops, force-push, data overwrites). | Llama-3.3-70B | plan |
| **EdgeCase** | Unhandled inputs / states / failure modes. | Llama-3.3-70B | plan |
| **Expectation** | Where the plan contradicts or ignores the product docs. Bridges technical steps → user wants. | Llama-3.3-70B | plan **+ docs** |
| **Arbiter** | Reconciles all 3 into the decision queue (suppress/keep/escalate). | DeepSeek-V3.1 | all findings + plan + docs |

Each specialist prompt enforces: a one-line role, hard exclusions ("you do NOT do X, another agent owns it"), labeled inputs, JSON-only output, and an anti-confabulation clause ("return empty if nothing found; do not invent issues").

---

## Output: the decision queue

The product is short by design — a user should grasp what needs them in under 10 seconds.

```
## Needs your decision (5)
1. [high] Dropping users table will delete all beta accounts, violating AUTH-103 — ... (plan: step 2)
2. [high] SHA-256 password hashing violates modern security standard (AUTH-101) — ... (plan: step 4)
...

## Auto-cleared (5)
5 items checked out across EdgeCase / Risk.
```

- **`needs_decision`** — surfaced, one line each. `disposition` is `keep` (genuine issue) or `escalate` (high-stakes + contested/unauthorized).
- **`auto_cleared`** — collapsed to a single line. Real findings the arbiter resolved for you (authorized by docs, neutralized by another agent, or minor). Each keeps a `reason` you can inspect with `QUORUM_DEBUG=1`.

---

## Setup

Requires [uv](https://docs.astral.sh/uv/) and a W&B account.

```bash
# 1. install deps
uv sync

# 2. add your W&B key
cp .env.example .env          # then paste your key from https://wandb.ai/authorize

# 3. (optional) sanity-check the connection
uv run smoke_test.py          # expects "✅ Connection works."
```

Models run on [W&B Inference](https://wandb.ai) (OpenAI-compatible). Tracing goes to [Weave](https://weave-docs.wandb.ai/). Your entity slug lives in `config.py`.

---

## Usage

```bash
# the product: run the full panel and print the decision queue
uv run main.py

# see everything — raw findings from each agent + the arbiter's full reasoning
QUORUM_DEBUG=1 uv run main.py

# test one specialist in isolation (fast iteration)
uv run run_agent.py risk        # or: edgecase | expectation
```

Each `main.py` run prints a live **Weave trace** URL — the nested view of `3 specialists → arbiter` is the demo centerpiece.

---

## Project structure

```
main.py              Entrypoint: load inputs → run_quorum → print queue (+ QUORUM_DEBUG dump)
quorum.py            Orchestrator: asyncio fan-out (3 specialists) → arbiter
render.py            Arbiter JSON → decision-queue markdown
config.py            Model IDs, W&B entity slug, paths (auto-loads .env)
tracing.py           Optional Weave wrapper (@op decorator + init; no-op if absent)
run_agent.py         Run one specialist in isolation
smoke_test.py        One-shot W&B connection check

agents/
  risk.py            Risk specialist (prompt + call)
  edgecase.py        EdgeCase specialist
  expectation.py     Expectation specialist (takes docs)
  arbiter.py         Arbiter (reconciliation)
  llm.py             Shared async client, JSON extraction, output coercion
  schemas.py         Data contracts (Finding / AgentOutput / ArbiterOutput)

inputs/
  plan.md            Demo plan (8-step auth feature with planted issues)
  expectations/      Demo product docs (Jira-style user stories + meeting notes)
```

### Data contract
Every specialist emits the same shape; `plan_section` is the join key the arbiter aligns on.
```json
{"findings":[{"severity":"high|med|low","issue":"...","plan_section":"step 2","why":"..."}]}
```

---

## Iterating

| To change… | Edit |
|---|---|
| What an agent looks for / its exclusions | `agents/<agent>.py` → `SYSTEM_PROMPT` |
| Reconciliation rules (suppress/keep/escalate) | `agents/arbiter.py` → `SYSTEM_PROMPT` |
| Models | `config.py` |
| The plan / docs under test | `inputs/plan.md`, `inputs/expectations/*.md` |
| Output format | `render.py` |

**Tips:** specialists run on `temperature=0`, but DeepSeek (arbiter) still wobbles run-to-run — re-run a few times when judging a prompt change. The architecture (`quorum.py`, `render.py`, `main.py`) is stable; iteration happens almost entirely in the prompt strings.

---

## Demo inputs (the planted answer key)

`inputs/plan.md` is an 8-step "add auth" plan seeded so the panel catches concrete things:

| Plan step | Issue | Caught by | Docs say | Arbiter |
|---|---|---|---|---|
| 2 — drop & recreate `users` | wipes ~4k beta accounts | Risk + Expectation | AUTH-103 forbids it | escalate |
| 3 — drop `temp_tokens` | destructive | Risk | meeting notes authorize | **suppress** |
| 4 — SHA-256 passwords | contradicts requirement | Expectation | AUTH-101 wants modern standard | keep |
| 6 — non-expiring JWT | contradicts requirement | Expectation | AUTH-102 wants ~24h | keep |
| 8 — force-push to `main` | destructive/irreversible | Risk | — | escalate* |

\* The arbiter occasionally auto-clears the force-push ("no explicit prohibition") instead of escalating — a known prompt-tuning target (see Status).

---

## Status

**Implemented & verified end-to-end:**
- ✅ Full pipeline: 3 parallel specialists → arbiter → rendered queue, all on real W&B Inference models
- ✅ Cross-agent merge, context-based suppression, finding compression
- ✅ Nested Weave tracing (logging live)
- ✅ Crash-proof JSON parsing + per-agent failure isolation
- ✅ Demo inputs with planted, catchable conflicts

**Not yet implemented:**
- ❌ Stretch goal: arbiter sends a finding *back* to an agent to re-evaluate (cyclic flow — likely LangGraph)
- ❌ CLI args (plan path hardcoded to `inputs/plan.md`)
- ❌ Tests

**Known weak spots:**
- ⚠️ Arbiter sometimes auto-clears unauthorized destructive ops (force-push) — tighten `agents/arbiter.py` so unauthorized destructive ops default to escalate
- ⚠️ Run-to-run variance from the arbiter model even at `temperature=0`

---

## Notes / decisions

- **Orchestration is plain `asyncio`, not LangGraph.** For a linear "3 → 1" flow, `asyncio.gather` is the fan-out and Weave provides the lineage; LangGraph would only earn its place for the cyclic stretch goal.
- **Model catalog drifts.** The original spec's `DeepSeek-V3-0324` / `Llama-4-Scout` are gone from W&B; the arbiter now runs on `DeepSeek-V3.1`. Check `config.py` against the live catalog if a call 404s.
