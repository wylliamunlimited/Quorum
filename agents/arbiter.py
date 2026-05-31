"""Arbiter — reconciles the three specialists' findings into a triaged queue.

This is the "why multi-agent" step. It is the only agent that sees everything:
all three findings lists, the plan, and the product docs. It cross-references
them and decides per finding — suppress / keep / escalate — then compresses to
the few items a human must actually see.

Runs on DeepSeek-V3 (the most reasoning-heavy step).
"""

import json

import config
from agents.llm import _SEVERITY, chat, extract_json
from agents.schemas import AgentOutput, ArbiterOutput
from tracing import op

AGENT_NAME = "Arbiter"

SYSTEM_PROMPT = """\
You are the ARBITER on a plan-review panel. Three specialist reviewers each \
independently reviewed the SAME software plan and produced JSON findings:
- RISK: destructive / irreversible operations.
- EDGECASE: unhandled inputs, states, and failure modes.
- EXPECTATION: contradictions with the product expectation docs.
You see ALL of their findings, the PLAN, and the product EXPECTATION DOCS.

Your job: reconcile everything into a SHORT decision queue for a busy project \
manager who wants to read as little as possible. For each finding, decide one:

- SUPPRESS -> goes in auto_cleared. The finding is real but resolved by context: \
the expectation docs or meeting notes explicitly authorize/request it, OR \
another agent's findings neutralize it, OR it is a minor low-severity nitpick \
not worth a human's time.
- KEEP -> goes in needs_decision with disposition "keep". A genuine issue the \
human should weigh, with no countervailing context.
- ESCALATE -> goes in needs_decision with disposition "escalate". High-stakes \
AND contested or unauthorized — especially when MULTIPLE agents flag the same \
step, or a destructive operation has no authorization anywhere in the docs.

Critical reconciliation rules:
- A destructive operation that the docs or meeting notes explicitly authorize -> \
SUPPRESS (the danger is real but approved). This is the key move: do not make \
the human re-decide something already agreed.
- A destructive operation authorized NOWHERE -> ESCALATE.
- If two agents flag the SAME plan step, MERGE them into ONE item and list both \
in source_agents. Agreement makes it MORE important, not redundant.
- A requirement contradiction with no override -> KEEP.
- Minor / low-severity edge cases -> usually SUPPRESS.
Be aggressive about auto-clearing. Only surface what genuinely needs a human.

For each needs_decision item, "why_you" is one line on why it needs THIS human \
(what's at stake / what to decide), referencing the relevant doc when useful.

Output ONLY a JSON object in exactly this shape, nothing before or after:
{"needs_decision":[{"severity":"high|med|low","issue":"<one line>","why_you":"<one line>","plan_section":"step <N>","source_agents":["Risk"],"disposition":"keep|escalate"}],"auto_cleared":[{"issue":"<one line>","plan_section":"step <N>","source_agents":["Risk"],"reason":"<one line: why safe to clear>"}]}

Do not invent findings no agent raised. Base everything on the findings and \
source material provided."""


def _coerce(data: dict) -> ArbiterOutput:
    """Force the model's JSON into a render-safe ArbiterOutput (no KeyErrors)."""
    nd = data.get("needs_decision", []) if isinstance(data, dict) else []
    ac = data.get("auto_cleared", []) if isinstance(data, dict) else []

    needs = []
    for d in nd:
        if not isinstance(d, dict):
            continue
        sev = str(d.get("severity", "med")).lower().strip()
        disp = d.get("disposition", "keep")
        agents = d.get("source_agents", [])
        needs.append({
            "severity": _SEVERITY.get(sev, "med"),
            "issue": str(d.get("issue", "")).strip(),
            "why_you": str(d.get("why_you", d.get("why", ""))).strip(),
            "plan_section": str(d.get("plan_section", "")).strip(),
            "source_agents": agents if isinstance(agents, list) else [],
            "disposition": disp if disp in ("keep", "escalate") else "keep",
        })

    cleared = []
    for c in ac:
        if not isinstance(c, dict):
            continue
        agents = c.get("source_agents", [])
        cleared.append({
            "issue": str(c.get("issue", "")).strip(),
            "plan_section": str(c.get("plan_section", "")).strip(),
            "source_agents": agents if isinstance(agents, list) else [],
            "reason": str(c.get("reason", "")).strip(),
        })

    return {"needs_decision": needs, "auto_cleared": cleared}


@op
async def run_arbiter(
    risk: AgentOutput,
    edgecase: AgentOutput,
    expectation: AgentOutput,
    plan: str,
    expectations: dict[str, str],
) -> ArbiterOutput:
    docs = "\n\n".join(
        f"--- {name} ---\n{content}" for name, content in expectations.items()
    )
    user = (
        "RISK FINDINGS:\n" + json.dumps(risk, indent=2) + "\n\n"
        "EDGECASE FINDINGS:\n" + json.dumps(edgecase, indent=2) + "\n\n"
        "EXPECTATION FINDINGS:\n" + json.dumps(expectation, indent=2) + "\n\n"
        "PLAN:\n" + plan + "\n\n"
        "EXPECTATION DOCS:\n" + docs
    )
    raw = await chat(config.ARBITER_MODEL, SYSTEM_PROMPT, user, temperature=0)
    try:
        return _coerce(extract_json(raw))
    except Exception as e:
        print(f"[Arbiter] could not parse model output ({e}); returning empty queue.")
        return {"needs_decision": [], "auto_cleared": []}
