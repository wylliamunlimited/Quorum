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
   (Expectation only)        ↑__________________│
                         routed re-evaluation (up to 3 rounds)
```

- **3 specialists run in parallel**, each with one narrow job (and explicit exclusions so they don't overlap).
- **The arbiter is the only agent that sees everything.** It cross-references the findings against each other and against the docs, then decides per finding: **suppress / keep / escalate**.
- **It iterates.** When the arbiter is uncertain about an item, it routes a targeted question (plus the cross-context the specialist didn't see) *back* to one specialist for a second look, then re-reconciles — up to 3 rounds, stopping as soon as nothing is contested. See [The confidence loop](#the-confidence-loop).
- The output is a **triaged queue**, not a document. Most findings auto-clear; only the contested ones surface.

The reconciliation is the "why multi-agent": e.g. Risk flags a `DROP TABLE` as dangerous, but the meeting notes authorized it → the arbiter **suppresses** it. Identical operation elsewhere with no authorization → **escalate**. No single agent can make that call.

---

## The agents

| Agent | Job (and *only* this) | Model | Input |
|---|---|---|---|
| **Risk** | Destructive / irreversible operations (drops, force-push, data overwrites). | Llama-3.3-70B | plan |
| **EdgeCase** | Unhandled inputs / states / failure modes. | Llama-3.3-70B | plan |
| **Requirement Farmer** | Distil the docs into a verified list of "what people want" (plan-independent). | Llama-3.3-70B | docs |
| **Expectation** | Judge the plan against each farmed requirement; for violations emit a **proposed fix**. | Llama-3.3-70B | plan **+ requirements** |
| **Arbiter** | Reconciles all findings into the decision queue (suppress/keep/escalate/re-evaluate). | DeepSeek-V3.1 | all findings + plan + docs |

Each specialist prompt enforces: a one-line role, hard exclusions ("you do NOT do X, another agent owns it"), labeled inputs, JSON-only output, and an anti-confabulation clause ("return empty if nothing found; do not invent issues").

**Expectation is a two-stage reasoning flow** (`farm → act`): the Farmer extracts verified requirements as a cited artifact, then the act-stage judges the plan against them and proposes grounded fixes. Separating *establish the fact* from *act on it* — and forcing the act-stage to cite the farmed requirement — improves accuracy and coverage. See [Reasoning flow](#reasoning-flow-expectation--farm--act).

---

## Output: the decision queue

The product is short by design — a user should grasp what needs them in under 10 seconds.

```
## Needs your decision (5)
1. [high] Dropping users table will delete all beta accounts, violating AUTH-103 — ... (plan: step 2)
   → proposed fix: alter the existing users table instead of dropping it
2. [high] SHA-256 password hashing violates modern security standard (AUTH-101) — ... (plan: step 4)
   → proposed fix: replace SHA-256 with bcrypt (work factor ≥ 12)
...

## Auto-cleared (5)
5 items checked out across EdgeCase / Risk.
```

- **`needs_decision`** — surfaced, one line each. `disposition` is `keep` (genuine issue) or `escalate` (high-stakes + contested/unauthorized). Items Expectation raised also carry a **`→ proposed fix:`** line — a concrete change the human can approve.
- **`auto_cleared`** — collapsed to a single line. Real findings the arbiter resolved for you (authorized by docs, neutralized by another agent, or minor). Each keeps a `reason` you can inspect with `QUORUM_DEBUG=1`.

---

## The confidence loop

Quorum doesn't decide everything in one shot — it iterates to make the triage *trustworthy*. The design (one coordinate in the iterative-multi-agent space):

- **Dependency = arbiter-routed.** Specialists stay blind to each other. When the arbiter is uncertain about an item, it emits a `reeval_request` naming **one** target specialist, a question, and the cross-context that specialist never saw. Only the arbiter sees everything; dependency flows *through* it, so the panel keeps its independence (no groupthink).
- **Target = confidence / triage stability.** Each round re-evaluates *only the contested items*; the `reeval_requests` list **is** the contested set. Converge when it's empty.
- **Stop rule = stability, hard cap 3 rounds** (`config.MAX_ROUNDS`). The final round forces a commit — enforced in code (`drop_reeval`), not just the prompt, so the loop physically cannot run away.

```
Round 1: 3 specialists → arbiter → {verdicts, reeval_requests}
   while contested and round < 3:
Round n: re-run ONLY targeted specialists (with routed context) → re-reconcile
   → converge (no requests) or hit the cap → commit
```

**Two safety guarantees on destructive operations** (because the arbiter, left alone, was overconfident — it auto-cleared an *unauthorized* force-push as "no doc forbids it"):

1. **Guardrail (orchestrator):** a destructive op may not be *silently* auto-cleared. Every destructive auto-clear gets exactly one forced second look — this is what reliably fires the loop.
2. **Authorization backstop (orchestrator):** to clear a destructive op the arbiter must cite a real `authorized_by` doc/note; any destructive clear whose citation doesn't verify against the actual docs is **escalated by policy**. Safety property: *no irreversible action is auto-dismissed without authorization on record.*

The result is the demo's money-shot — same operation type, opposite outcomes, decided by the docs:

```
step 8 (force-push):  contested round 1 (→ Expectation) → needs_decision / escalate
step 3 (temp_tokens): contested round 1 (→ Expectation) → auto_cleared
```

Run `QUORUM_DEBUG=1 uv run main.py` to see the per-round requests and this contested-item lifecycle; the nested rounds also show up in the Weave trace.

---

## Reasoning flow: Expectation = farm → act

Expectation is a two-stage mini-pipeline, not a single call — a small "network within the network":

```
docs ──► Requirement Farmer ──► [verified requirements]
                                       │ (cited artifact)
plan ──────────────────────────────────┼──► Expectation act-stage ──► findings + proposed_fix
```

- **Farm** (`run_requirement_farmer`, docs-only): distil the docs into atomic, sourced requirements — *"what do people want"* — independent of the plan. Farmed once, up front in `run_quorum`.
- **Act** (`run_expectation_agent`): judge the plan against each requirement; for violations emit a finding with a concrete **`proposed_fix`** that cites the requirement (e.g. *AUTH-101 → "replace SHA-256 with bcrypt, work factor ≥ 12"*).

**Why it improves accuracy:** separating *establish a verified fact* from *act on it* — and forcing the act-stage to cite the farmed requirement — constrains the judgment to a checkable premise (the same principle as the authorization backstop). Judging *per requirement* also improves coverage. The **proposed fix** is stitched onto the surfaced item in code (`_attach_proposed_fixes`, matched by `plan_section` and gated to Expectation-raised items) so it can't be lost or mis-paired in reconciliation.

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

## Use from Claude Code (MCP)

Quorum runs as a local MCP server (`quorum_mcp.py`) exposing one tool, **`review_plan`**, so Claude Code can review a plan it drafts and surface the clarifications before you approve:

```
Claude drafts a plan ──► review_plan(plan, expectations_dir?) ──► "Needs your decision (N)" + proposed fixes ──► Claude asks you
```

Quorum still runs its own W&B agents — Claude Code is the **caller**, not the reviewer.

**This repo (project scope):** `.mcp.json` already registers the server. Start `claude` here and approve the `quorum` server when prompted; then ask Claude to review a plan.

**Any repo (user scope):**
```bash
claude mcp add quorum -- uv run --directory /Users/wylliamcheng/Desktop/directories/Quorum quorum_mcp.py
```
Pass that repo's own docs via `expectations_dir` (e.g. `.quorum/expectations`); it defaults to Quorum's bundled `inputs/expectations/`.

**Test without Claude Code:** `uv run mcp dev quorum_mcp.py` (MCP Inspector), or call the tool directly:
```bash
uv run python -c "import asyncio; from quorum_mcp import review_plan; from main import load_plan; print(asyncio.run(review_plan(load_plan())))"
```

> A full review is ~30–90s (farm + panel + re-eval rounds) — fine for a prototype; a single-pass `fast` mode is a noted follow-up.

---

## Project structure

```
main.py              Entrypoint: load inputs → run_quorum → print queue (+ QUORUM_DEBUG dump & iteration lifecycle)
quorum.py            Orchestrator: bounded confidence loop (fan-out → arbiter → re-eval rounds) + destructive-op guardrails
render.py            Arbiter JSON → decision-queue markdown
config.py            Model IDs, W&B entity slug, paths (auto-loads .env)
tracing.py           Optional Weave wrapper (@op decorator + init; no-op if absent)
run_agent.py         Run one specialist in isolation
smoke_test.py        One-shot W&B connection check
quorum_mcp.py        Local MCP server (review_plan tool) for Claude Code
.mcp.json            Registers the MCP server (project scope)

agents/
  risk.py            Risk specialist (prompt + call)
  edgecase.py        EdgeCase specialist
  expectation.py     Requirement Farmer + Expectation act-stage (farm → act, proposes fixes)
  arbiter.py         Arbiter (reconciliation)
  llm.py             Shared async client, JSON extraction, output coercion, RE-EVALUATION prompt
  schemas.py         Data contracts (Requirement / Finding / AgentOutput / ReevalRequest / ArbiterOutput)

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
| Reconciliation rules (suppress/keep/escalate/re-evaluate) | `agents/arbiter.py` → `SYSTEM_PROMPT` |
| Round cap / loop behavior | `config.MAX_ROUNDS`; loop in `quorum.py` |
| Destructive-op safety (guardrail + authorization backstop) | `quorum.py` → `_guardrail_requests`, `_enforce_destructive_authorization` |
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
| 8 — force-push to `main` | destructive/irreversible | Risk | — (nothing authorizes it) | escalate* |

\* DeepSeek alone is overconfident and auto-clears the force-push ("no doc forbids it"). The [confidence loop](#the-confidence-loop) fixes this: step 8 is contested in round 1, re-evaluated, and escalated by the authorization backstop (no citable doc) — while step 3 stays suppressed because the meeting notes authorize it.

---

## Status

**Implemented & verified end-to-end:**
- ✅ Full pipeline: 3 parallel specialists → arbiter → rendered queue, all on real W&B Inference models
- ✅ **Bounded confidence loop** — arbiter-routed re-evaluation, up to 3 rounds, stops on stability (`config.MAX_ROUNDS`); final-round commit enforced in code
- ✅ **Destructive-op safety** — guardrail (no silent auto-clear) + authorization backstop (escalate any clear without a verifiable doc citation)
- ✅ **Expectation reasoning flow** — farm (verified requirements) → act (judge + propose fixes); fixes stitched onto surfaced items in code
- ✅ **Claude Code integration** — local MCP server (`quorum_mcp.py`, `review_plan` tool); Claude calls it on a plan and surfaces the decision queue
- ✅ Cross-agent merge, context-based suppression, finding compression
- ✅ Nested Weave tracing (logging live) + per-round iteration lifecycle in `QUORUM_DEBUG`
- ✅ Crash-proof JSON parsing + per-agent failure isolation
- ✅ Demo inputs with planted, catchable conflicts (force-push now reliably escalates)

**Not yet implemented:**
- ❌ CLI args (plan path hardcoded to `inputs/plan.md`)
- ❌ Tests

**Known weak spots:**
- ⚠️ **Arbiter severity calibration is unstable** — run-to-run it swings between escalate-happy (queue grows to ~8–9 items, including minor edge cases) and over-clearing (it has auto-cleared real AUTH-101/102 violations). The farm→act split made Expectation's *findings* sharper, but the *arbiter's* reconciliation is the volatile layer. Top tuning target in `agents/arbiter.py`.
- ⚠️ Run-to-run variance from the arbiter model even at `temperature=0` — the loop dampens it but the queue can still wobble.

---

## Notes / decisions

- **Orchestration is plain `asyncio`, not LangGraph** — including the cyclic re-evaluation loop. `asyncio.gather` is the fan-out, a `while` loop drives the rounds, and Weave provides the lineage. LangGraph would only earn its place for a more complex graph (many node types, conditional branching beyond this single routed loop).
- **Dependency is arbiter-routed, not peer-to-peer.** Chosen deliberately over a peer-visible "mesh" to preserve the specialists' independence (the asset that makes the panel worth having). The arbiter is the single router.
- **Destructive ops get a code-enforced safety net.** The arbiter (DeepSeek) was overconfident about an unauthorized force-push, and prompting alone didn't fix it. So clearing a destructive op now requires a *verifiable* `authorized_by` citation; the orchestrator escalates anything that doesn't check out. Confidence isn't left entirely to the model's judgment on irreversible actions.
- **Model catalog drifts.** The original spec's `DeepSeek-V3-0324` / `Llama-4-Scout` are gone from W&B; the arbiter now runs on `DeepSeek-V3.1`. Check `config.py` against the live catalog if a call 404s.
