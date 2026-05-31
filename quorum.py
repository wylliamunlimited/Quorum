"""Orchestrator — the top-level flow.

run_quorum is deliberately the single entrypoint: in step 5 it becomes the root
@weave.op(), and because it calls the four agent ops inside it, Weave renders
the whole panel (3 parallel specialists -> arbiter) as one nested trace.

asyncio.gather runs the three specialists concurrently; the arbiter awaits all
three before reconciling.
"""

import asyncio

from agents.arbiter import run_arbiter
from agents.edgecase import run_edgecase_agent
from agents.expectation import run_expectation_agent
from agents.risk import run_risk_agent
from tracing import op


@op
async def run_quorum(plan: str, expectations: dict[str, str]) -> dict:
    # Fan-out: three narrow specialists, in parallel. Expectation also gets docs.
    risk, edgecase, expectation = await asyncio.gather(
        run_risk_agent(plan),
        run_edgecase_agent(plan),
        run_expectation_agent(plan, expectations),
    )

    # Reconcile: the arbiter sees all three findings + the source material.
    arbiter = await run_arbiter(risk, edgecase, expectation, plan, expectations)

    # Return intermediates too — useful for debugging now, and Weave surfaces
    # them as child spans later.
    return {
        "risk": risk,
        "edgecase": edgecase,
        "expectation": expectation,
        "arbiter": arbiter,
    }
