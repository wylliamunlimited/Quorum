"""Orchestrator — the bounded confidence loop.

run_quorum is the single root @weave.op(). It runs the panel in rounds:

  Round 1: 3 specialists fan out in parallel (blind to each other) -> arbiter.
  Then, while the arbiter still has contested items (reeval_requests) and we are
  under the round cap: re-run ONLY the targeted specialists with the arbiter's
  routed context, merge their revised findings back, and re-reconcile. The
  arbiter must commit on the final round, so the loop always terminates with a
  fully decided queue.

Dependency is arbiter-routed: specialists never see each other directly, only
the specific cross-context the arbiter chooses to route to them.
"""

import asyncio
import re

import config
from agents.arbiter import run_arbiter
from agents.edgecase import run_edgecase_agent
from agents.expectation import run_expectation_agent, run_requirement_farmer
from agents.risk import run_risk_agent
from agents.schemas import AgentOutput, ReevalRequest, Requirements
from tracing import op


def _section_key(s: str) -> str:
    """Normalize a plan_section so the same step matches across rounds.

    "Step 4", "step 4: force-push", "step  4" all collapse to "step 4". Anything
    that doesn't look like 'step N' falls back to whitespace-collapsed lowercase.
    """
    s = (s or "").lower().strip()
    m = re.match(r"step\s*(\d+)", s)
    if m:
        return f"step {m.group(1)}"
    return re.sub(r"\s+", " ", s)


def _build_reeval_block(requests: list[ReevalRequest]) -> str:
    """Build the labeled block injected into one specialist's user message.

    `requests` are all the arbiter's requests targeting THIS agent this round.
    """
    lines = ["RE-EVALUATION REQUEST (the arbiter is uncertain and wants your view):"]
    for r in requests:
        lines.append(f"- Plan section in question: {r['plan_section']}")
        lines.append(f"  The arbiter's question: {r['question']}")
        lines.append(
            "  Cross-context routed to you (you did not see this on your first "
            f"pass): {r['context']}"
        )
    lines.append(
        "Re-examine ONLY the section(s) named above through YOUR lens, and return "
        "your full findings for those section(s): revise, keep, or withdraw."
    )
    return "\n".join(lines)


def _merge_findings(
    old: AgentOutput, revised: AgentOutput, requests: list[ReevalRequest]
) -> AgentOutput:
    """Replace the targeted sections' findings; keep everything else untouched.

    A withdrawn finding (agent returns nothing for a targeted section) correctly
    disappears — that's valid convergence, not a bug.
    """
    targeted = {_section_key(r["plan_section"]) for r in requests}
    kept = [f for f in old["findings"] if _section_key(f["plan_section"]) not in targeted]
    new = [f for f in revised["findings"] if _section_key(f["plan_section"]) in targeted]
    return {"findings": kept + new}


async def _rerun_agent(
    agent_name: str,
    requests: list[ReevalRequest],
    plan: str,
    requirements: Requirements,
) -> AgentOutput:
    """Re-invoke one specialist with the arbiter's routed context."""
    ctx = _build_reeval_block(requests)
    if agent_name == "Risk":
        return await run_risk_agent(plan, ctx)
    if agent_name == "EdgeCase":
        return await run_edgecase_agent(plan, ctx)
    return await run_expectation_agent(plan, requirements, ctx)


def _guardrail_requests(
    arbiter: dict, risk: AgentOutput, reevaluated: set[str]
) -> list[ReevalRequest]:
    """Policy guardrail: a destructive operation may not be SILENTLY auto-cleared.

    The arbiter triggers re-evaluation on its own uncertainty — but an overconfident
    auto-clear of a destructive op (the force-push case) is a blind spot self-doubt
    won't catch. So we force exactly one routed second look at any destructive
    auto-clear (a section Risk flagged) that hasn't already been re-evaluated. The
    arbiter still decides the outcome; we only guarantee the look happens.
    """
    destructive = {_section_key(f["plan_section"]) for f in risk["findings"]}
    already = {_section_key(r["plan_section"]) for r in arbiter.get("reeval_requests", [])}
    extra: list[ReevalRequest] = []
    for c in arbiter.get("auto_cleared", []):
        k = _section_key(c["plan_section"])
        if k in destructive and k not in reevaluated and k not in already:
            extra.append({
                "target_agent": "Expectation",
                "plan_section": c["plan_section"],
                "question": (
                    "Does any expectation doc or meeting note authorize this "
                    "destructive operation? If nothing authorizes it, it must "
                    "escalate — it cannot be auto-cleared."
                ),
                "context": (
                    f"Risk flagged this as destructive/irreversible; the arbiter "
                    f"auto-cleared it (reason: {c['reason']}). Authorization must "
                    "come from a doc or note, not the plan's own wording."
                ),
            })
    return extra


def _authorization_tokens(expectations: dict[str, str]) -> set[str]:
    """Strings that count as a real authorization source (doc names + note words)."""
    tokens = {"note", "notes", "meeting", "standup", "sync"}
    for name in expectations:
        base = name.lower().rsplit(".", 1)[0]      # "auth-103", "meeting-notes"
        tokens.add(base)
        tokens.add(base.replace("-", " "))
        tokens.add(base.replace("-", ""))
    return tokens


def _enforce_destructive_authorization(
    arbiter: dict, risk: AgentOutput, expectations: dict[str, str]
) -> dict:
    """Safety backstop: an irreversible action may not be auto-dismissed unless the
    arbiter cited a real expectation doc/note that authorizes it.

    Run once after the loop converges. Any cleared destructive op whose
    authorized_by can't be verified against the actual docs is moved to
    needs_decision as an escalation — the model cannot silently clear it.
    """
    destructive = {_section_key(f["plan_section"]) for f in risk["findings"]}
    tokens = _authorization_tokens(expectations)
    kept, escalated = [], []
    for c in arbiter.get("auto_cleared", []):
        cite = (c.get("authorized_by") or "").lower()
        verified = bool(cite) and any(t in cite for t in tokens)
        if _section_key(c["plan_section"]) in destructive and not verified:
            escalated.append({
                "severity": "high",
                "issue": c["issue"],
                "why_you": (
                    "Destructive/irreversible operation with no authorization on "
                    "record in any doc or note — confirm before it runs."
                ),
                "plan_section": c["plan_section"],
                "source_agents": c.get("source_agents", []),
                "disposition": "escalate",
            })
        else:
            kept.append(c)
    if not escalated:
        return arbiter
    return {
        **arbiter,
        "needs_decision": arbiter.get("needs_decision", []) + escalated,
        "auto_cleared": kept,
    }


def _attach_proposed_fixes(arbiter: dict, expectation: AgentOutput) -> dict:
    """Stitch each surfaced item's proposed_fix from the originating Expectation
    finding, matched by plan_section.

    Done in code (not via the arbiter) so a concrete fix can't be lost or mangled
    in reconciliation — same robustness pattern as the authorization backstop.
    """
    fixes = {
        _section_key(f["plan_section"]): f["proposed_fix"]
        for f in expectation["findings"]
        if f.get("proposed_fix")
    }
    if not fixes:
        return arbiter
    needs = []
    for d in arbiter.get("needs_decision", []):
        # Only attach to items Expectation actually raised — a different agent's
        # finding at the same step shouldn't inherit Expectation's fix.
        eligible = "Expectation" in d.get("source_agents", [])
        fix = fixes.get(_section_key(d["plan_section"])) if eligible else None
        needs.append({**d, "proposed_fix": fix} if fix else d)
    return {**arbiter, "needs_decision": needs}


@op
async def run_quorum(plan: str, expectations: dict[str, str]) -> dict:
    # Farm verified requirements once, up front — the cited artifact the
    # Expectation act-stage judges the plan against (round 1 and every re-eval).
    requirements = await run_requirement_farmer(expectations)

    # Round 1: full fan-out — three narrow specialists in parallel.
    risk, edgecase, expectation = await asyncio.gather(
        run_risk_agent(plan),
        run_edgecase_agent(plan),
        run_expectation_agent(plan, requirements),
    )
    findings = {"Risk": risk, "EdgeCase": edgecase, "Expectation": expectation}
    reevaluated: set[str] = set()  # sections that have had their forced second look

    round_num = 1
    arbiter = await run_arbiter(
        findings["Risk"], findings["EdgeCase"], findings["Expectation"],
        plan, expectations, round_num=round_num,
    )
    if round_num < config.MAX_ROUNDS:
        arbiter["reeval_requests"] = list(arbiter.get("reeval_requests", [])) + \
            _guardrail_requests(arbiter, findings["Risk"], reevaluated)
    history = [{"round": round_num, "reeval_requests": arbiter.get("reeval_requests", [])}]

    # Confidence loop: re-evaluate only contested items until stable (capped).
    while arbiter.get("reeval_requests") and round_num < config.MAX_ROUNDS:
        round_num += 1

        # Group the arbiter's requests by which specialist should resolve them.
        by_agent: dict[str, list[ReevalRequest]] = {}
        for r in arbiter["reeval_requests"]:
            reevaluated.add(_section_key(r["plan_section"]))
            by_agent.setdefault(r["target_agent"], []).append(r)

        # Re-run only the targeted specialists, in parallel, with routed context.
        names = list(by_agent.keys())
        outs = await asyncio.gather(
            *(_rerun_agent(a, by_agent[a], plan, requirements) for a in names)
        )

        # Merge revised findings back (targeted sections only).
        for name, out in zip(names, outs):
            findings[name] = _merge_findings(findings[name], out, by_agent[name])

        # Re-reconcile with round number + prior dispositions as the anchor.
        # On the final round the arbiter is forced to commit (no more requests).
        prior = arbiter
        arbiter = await run_arbiter(
            findings["Risk"], findings["EdgeCase"], findings["Expectation"],
            plan, expectations, round_num=round_num, prior=prior,
        )
        if round_num < config.MAX_ROUNDS:
            arbiter["reeval_requests"] = list(arbiter.get("reeval_requests", [])) + \
                _guardrail_requests(arbiter, findings["Risk"], reevaluated)
        history.append(
            {"round": round_num, "reeval_requests": arbiter.get("reeval_requests", [])}
        )

    # Backstop: escalate any cleared destructive op without a verifiable citation.
    arbiter = _enforce_destructive_authorization(arbiter, findings["Risk"], expectations)
    # Stitch concrete fixes onto surfaced items from the Expectation findings.
    arbiter = _attach_proposed_fixes(arbiter, findings["Expectation"])

    return {
        "risk": findings["Risk"],
        "edgecase": findings["EdgeCase"],
        "expectation": findings["Expectation"],
        "requirements": requirements,
        "arbiter": arbiter,
        "rounds": round_num,
        "history": history,
    }
