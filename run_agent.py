"""Run a single specialist agent in isolation and print its findings.

Lets us verify each agent as we convert it from stub to real, without the
arbiter (still a stub) hiding the output.

Usage:
  uv run run_agent.py risk
  uv run run_agent.py edgecase
  uv run run_agent.py expectation
"""

import asyncio
import json
import sys

from main import load_expectations, load_plan
from agents.edgecase import run_edgecase_agent
from agents.expectation import run_expectation_agent
from agents.risk import run_risk_agent


async def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "risk"
    plan = load_plan()
    docs = load_expectations()

    if which == "risk":
        out = await run_risk_agent(plan)
    elif which == "edgecase":
        out = await run_edgecase_agent(plan)
    elif which == "expectation":
        out = await run_expectation_agent(plan, docs)
    else:
        raise SystemExit(f"unknown agent '{which}' (use: risk | edgecase | expectation)")

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
