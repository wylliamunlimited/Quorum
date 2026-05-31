"""Quorum entrypoint.

STEP 2 (current): run the full pipeline end-to-end on STUB agents (no LLM calls
yet) and print the triaged decision queue. This proves the orchestration —
fan-out -> arbiter -> rendered markdown — before any model is wired in.

Set QUORUM_DEBUG=1 to also dump every raw agent finding behind the queue.
"""

import asyncio
import json
import os
from pathlib import Path

import config
import tracing
from quorum import run_quorum
from render import render_decision_queue


def load_plan(path: str = config.PLAN_PATH) -> str:
    return Path(path).read_text(encoding="utf-8")


def load_expectations(directory: str = config.EXPECTATIONS_DIR) -> dict[str, str]:
    docs: dict[str, str] = {}
    for p in sorted(Path(directory).glob("*.md")):
        docs[p.name] = p.read_text(encoding="utf-8")
    return docs


def main() -> None:
    tracing.init(config.WEAVE_PROJECT)

    plan = load_plan()
    expectations = load_expectations()

    result = asyncio.run(run_quorum(plan, expectations))

    print(render_decision_queue(result["arbiter"]))

    if os.environ.get("QUORUM_DEBUG"):
        print("\n" + "=" * 70)
        print("DEBUG — raw agent findings (pre-arbiter)")
        print("=" * 70)
        for agent in ("risk", "edgecase", "expectation"):
            print(f"\n[{agent}]")
            print(json.dumps(result[agent], indent=2))
        print("\n[arbiter] full reconciliation (incl. why each item was cleared)")
        print(json.dumps(result["arbiter"], indent=2))


if __name__ == "__main__":
    main()
