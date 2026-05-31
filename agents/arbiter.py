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
You see ALL of their findings, the PLAN, and the product EXPECTATION DOCS. The \
specialists are blind to each other — only YOU see everything, so cross-context \
reasoning is your job.

Your job: reconcile everything into a SHORT decision queue for a busy project \
manager who wants to read as little as possible. For each finding, decide one of:

- SUPPRESS -> goes in auto_cleared. The finding is real but resolved by context: \
the expectation docs or meeting notes explicitly authorize/request it, OR \
another agent's findings neutralize it, OR it is a minor low-severity nitpick \
not worth a human's time.
- KEEP -> goes in needs_decision with disposition "keep". A genuine issue the \
human should weigh, with no countervailing context.
- ESCALATE -> goes in needs_decision with disposition "escalate". High-stakes \
AND contested or unauthorized — especially when MULTIPLE agents flag the same \
step, or a destructive operation has no authorization anywhere in the docs.
- RE-EVALUATE -> goes in reeval_requests. Use this ONLY when you are genuinely \
UNCERTAIN about an item AND another specialist's lens would resolve it. Rather \
than guess, route the item to the ONE specialist best placed to settle it, with \
a specific question and the cross-context they did not see on their first pass. \
Do NOT request re-evaluation for items you can already decide confidently.

Critical reconciliation rules:
- A destructive operation that the docs or meeting notes explicitly authorize -> \
SUPPRESS (the danger is real but approved). Do not make the human re-decide \
something already agreed.
- AUTHORIZATION RULE (critical): a destructive/irreversible operation may be \
SUPPRESSED only if a specific EXPECTATION DOC or MEETING NOTE authorizes it. The \
PLAN's own wording — calling a step "cleanup", "tidy", "safe", or similar — is \
NOT authorization; the plan is the very thing under review, so it cannot \
authorize itself. If you are about to auto-clear a destructive operation but \
cannot cite a doc or note that authorizes it, do NOT clear it: on a NON-FINAL \
round you MUST RE-EVALUATE it (route to Expectation, question: "Does any \
expectation doc or meeting note authorize this destructive operation? If none \
does, it should be escalated."); on the FINAL round, ESCALATE it.
- If two agents flag the SAME plan step, MERGE them into ONE item and list both \
in source_agents. Agreement makes it MORE important, not redundant.
- A requirement contradiction with no override -> KEEP.
- Minor / low-severity edge cases -> usually SUPPRESS.
Aggressively auto-clear what is genuinely safe; reserve RE-EVALUATE for real \
uncertainty so the loop converges quickly.

You run in ROUNDS (max 3). On a later round you receive PRIOR ROUND DISPOSITIONS \
plus the specialists' re-examined findings. Revisit ONLY the items you previously \
sent for re-evaluation; keep your prior decisions on everything else. On the \
FINAL round you MUST commit: emit an empty reeval_requests and place every item \
in needs_decision or auto_cleared.

For each needs_decision item, "why_you" is one line on why it needs THIS human \
(what's at stake / what to decide), referencing the relevant doc when useful.

ACCOUNTABILITY: whenever you SUPPRESS a DESTRUCTIVE/irreversible operation \
(a step Risk flagged), you MUST set "authorized_by" to the EXACT expectation doc \
or meeting note that authorizes it (e.g. "meeting notes" or "AUTH-103"). If you \
cannot name a real source from the EXPECTATION DOCS, leave authorized_by empty \
and do NOT suppress it. The plan itself is never a valid authorization.

Output ONLY a JSON object in exactly this shape, nothing before or after:
{"needs_decision":[{"severity":"high|med|low","issue":"<one line>","why_you":"<one line>","plan_section":"step <N>","source_agents":["Risk"],"disposition":"keep|escalate"}],"auto_cleared":[{"issue":"<one line>","plan_section":"step <N>","source_agents":["Risk"],"reason":"<one line: why safe to clear>","authorized_by":"<doc/note that authorizes it, or empty>"}],"reeval_requests":[{"target_agent":"Risk|EdgeCase|Expectation","plan_section":"step <N>","question":"<one line>","context":"<one line: the finding/context to route>"}]}

reeval_requests may be an empty list. Do not invent findings no agent raised. \
Base everything on the findings and source material provided."""


# Tolerant mapping of model-emitted target names to the canonical agent names.
_AGENT_NAMES = {
    "risk": "Risk",
    "edgecase": "EdgeCase",
    "edge": "EdgeCase",
    "expectation": "Expectation",
    "expect": "Expectation",
}


def _coerce(data: dict, drop_reeval: bool = False) -> ArbiterOutput:
    """Force the model's JSON into a render-safe ArbiterOutput (no KeyErrors).

    When drop_reeval is True (the final round) any re-eval requests are
    discarded, guaranteeing the loop terminates with a fully decided queue
    even if the model ignores the final-round instruction.
    """
    nd = data.get("needs_decision", []) if isinstance(data, dict) else []
    ac = data.get("auto_cleared", []) if isinstance(data, dict) else []
    rr = data.get("reeval_requests", []) if isinstance(data, dict) else []

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
            "authorized_by": str(c.get("authorized_by", "")).strip(),
        })

    requests = []
    if not drop_reeval:
        for r in rr:
            if not isinstance(r, dict):
                continue
            raw_target = str(r.get("target_agent", "")).lower().strip().replace(" ", "")
            target = _AGENT_NAMES.get(raw_target)
            if target is None:  # unroutable target — drop so group-by never breaks
                continue
            requests.append({
                "target_agent": target,
                "plan_section": str(r.get("plan_section", "")).strip(),
                "question": str(r.get("question", "")).strip(),
                "context": str(r.get("context", "")).strip(),
            })

    return {
        "needs_decision": needs,
        "auto_cleared": cleared,
        "reeval_requests": requests,
    }


@op
async def run_arbiter(
    risk: AgentOutput,
    edgecase: AgentOutput,
    expectation: AgentOutput,
    plan: str,
    expectations: dict[str, str],
    round_num: int = 1,
    prior: ArbiterOutput | None = None,
) -> ArbiterOutput:
    docs = "\n\n".join(
        f"--- {name} ---\n{content}" for name, content in expectations.items()
    )
    is_final = round_num >= config.MAX_ROUNDS
    user = (
        "RISK FINDINGS:\n" + json.dumps(risk, indent=2) + "\n\n"
        "EDGECASE FINDINGS:\n" + json.dumps(edgecase, indent=2) + "\n\n"
        "EXPECTATION FINDINGS:\n" + json.dumps(expectation, indent=2) + "\n\n"
        "PLAN:\n" + plan + "\n\n"
        "EXPECTATION DOCS:\n" + docs + "\n\n"
        f"ROUND: {round_num} of {config.MAX_ROUNDS}."
    )
    if prior is not None:
        prior_view = {
            "needs_decision": prior.get("needs_decision", []),
            "auto_cleared": prior.get("auto_cleared", []),
        }
        user += (
            "\n\nPRIOR ROUND DISPOSITIONS (keep these unless you re-examined the "
            "item this round):\n" + json.dumps(prior_view, indent=2)
        )
    if is_final:
        user += (
            "\n\nThis is the FINAL round. You MUST commit: emit an empty "
            "reeval_requests and place every item in needs_decision or auto_cleared."
        )

    raw = await chat(config.ARBITER_MODEL, SYSTEM_PROMPT, user, temperature=0)
    try:
        return _coerce(extract_json(raw), drop_reeval=is_final)
    except Exception as e:
        print(f"[Arbiter] could not parse model output ({e}); returning empty queue.")
        return {"needs_decision": [], "auto_cleared": [], "reeval_requests": []}
