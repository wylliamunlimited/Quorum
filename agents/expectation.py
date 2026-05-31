"""Expectation agent — a two-stage reasoning flow (farm -> act).

The agent is split so each step is grounded and checkable:

  1. FARM  (run_requirement_farmer): read ONLY the docs, distil the verified
     requirements — "what do people want" — as a plan-independent artifact.
  2. ACT   (run_expectation_agent):  judge the plan against each farmed
     requirement and, for violations, emit a concrete proposed fix that cites
     the requirement it's grounded in.

Separating "establish the fact" from "act on it" (and forcing the act-stage to
cite the farmed requirement) is what improves accuracy — the same principle as
the authorization backstop. Judging per-requirement also improves coverage.
"""

import config
from agents.llm import REEVAL_INSTRUCTION, chat, coerce_agent_output, extract_json
from agents.schemas import AgentOutput, Requirements
from tracing import op

AGENT_NAME = "Expectation"

# --- Stage 1: farm verified requirements from the docs (plan-independent) -----
FARMER_SYSTEM_PROMPT = """\
You are the REQUIREMENT FARMER. Read the product expectation docs (tickets + \
meeting notes) and extract the concrete things users and the product WANT — the \
"what do people want" — as a clean, verified list. You are plan-independent: you \
are NOT looking at any plan, only distilling the docs.

For each distinct want:
- source: the doc it comes from — a ticket id like "AUTH-101", or "meeting-notes".
- requirement: ONE clear sentence stating what is wanted, in plain user-facing \
terms (the outcome, not the implementation).

Keep each requirement atomic (one want each); merge duplicates. Capture explicit \
acceptance criteria AND clear wants stated in prose/notes.

Output ONLY a JSON object in exactly this shape, nothing before or after:
{"requirements":[{"source":"AUTH-101","requirement":"<one sentence>"}]}

Do not invent requirements the docs do not support. Skip a doc that states \
nothing actionable."""


def coerce_requirements(data: dict) -> Requirements:
    """Harden the farmer's JSON into the strict Requirements shape."""
    reqs = data.get("requirements", []) if isinstance(data, dict) else []
    out: Requirements = []
    for r in reqs:
        if not isinstance(r, dict):
            continue
        text = str(r.get("requirement", "")).strip()
        if not text:
            continue
        out.append({"source": str(r.get("source", "")).strip(), "requirement": text})
    return out


@op
async def run_requirement_farmer(expectations: dict[str, str]) -> Requirements:
    docs = "\n\n".join(
        f"--- {name} ---\n{content}" for name, content in expectations.items()
    )
    user = f"EXPECTATION DOCS:\n{docs}"
    raw = await chat(config.EXPECTATION_MODEL, FARMER_SYSTEM_PROMPT, user, temperature=0)
    try:
        return coerce_requirements(extract_json(raw))
    except Exception as e:
        print(f"[Farmer] could not parse model output ({e}); returning no requirements.")
        return []


# --- Stage 2: judge the plan against the farmed requirements, propose fixes ----
SYSTEM_PROMPT = """\
You are the EXPECTATION reviewer (second stage). You are given the PLAN and a \
list of verified REQUIREMENTS already farmed from the product docs. Your single \
job: for EACH requirement, decide whether the plan would DELIVER or VIOLATE it, \
and flag the violations.

THE BRIDGE: the PLAN is engineer-written and technical; the REQUIREMENTS are \
plain user/product wants. Use ordinary domain knowledge to connect a technical \
step to its user-facing effect. Examples:
- "drop and recreate the users table" destroys existing accounts -> violates a \
want that existing users must not be lost.
- hashing passwords with a fast hash (SHA-256/MD5) is crackable in a breach -> \
violates a want for passwords safe even if the database leaks.
- a token with no expiry keeps a session open forever -> violates a want that \
sessions end after a while.

For every requirement the plan VIOLATES or IGNORES, emit one finding:
- plan_section: the step responsible (e.g. "step 4").
- why: one sentence, citing the requirement's source (e.g. "AUTH-101: ...").
- proposed_fix: a concrete, MINIMAL change to the plan that would satisfy the \
requirement (e.g. "Replace SHA-256 with bcrypt (work factor >= 12) in step 4").

Stay in your lane: you do NOT flag destructive operations for being destructive \
(Risk owns that) or generic edge cases (EdgeCase owns that) — only violations of \
the given requirements.

Output ONLY a JSON object in exactly this shape, nothing before or after:
{"findings":[{"severity":"high|med|low","issue":"<one line>","plan_section":"step <N>","why":"<one sentence citing the requirement source>","proposed_fix":"<one concrete change>"}]}

If the plan satisfies every requirement, return {"findings":[]}. Do not invent \
issues to seem useful.""" + REEVAL_INSTRUCTION


@op
async def run_expectation_agent(
    plan: str, requirements: Requirements, context: str | None = None
) -> AgentOutput:
    reqs = "\n".join(
        f"- [{r['source']}] {r['requirement']}" for r in requirements
    ) or "(none farmed)"
    user = f"PLAN:\n{plan}\n\nREQUIREMENTS (verified, from the docs):\n{reqs}"
    if context:
        user += f"\n\n{context}"
    raw = await chat(config.EXPECTATION_MODEL, SYSTEM_PROMPT, user, temperature=0)
    try:
        return coerce_agent_output(extract_json(raw))
    except Exception as e:
        print(f"[Expectation] could not parse model output ({e}); returning no findings.")
        return {"findings": []}
