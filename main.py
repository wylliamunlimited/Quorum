"""Quorum entrypoint.

Runs the iterative confidence loop (3 specialists -> arbiter, repeated until the
triage converges or hits the round cap) and prints the triaged decision queue.

Set QUORUM_DEBUG=1 to also dump every raw agent finding, the full arbiter
reconciliation, the per-round re-evaluation history, and a lifecycle summary of
each contested item.
"""

import asyncio
import json
import os
from pathlib import Path

import config
import tracing
from quorum import _section_key, run_quorum
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

        _print_iteration_summary(result)


def _print_iteration_summary(result: dict) -> None:
    """Show how the confidence loop ran: rounds, re-eval requests, and where each
    contested item finally landed."""
    history = result.get("history", [])
    print("\n" + "=" * 70)
    print(f"ITERATION — {result.get('rounds', 1)} round(s)")
    print("=" * 70)

    for h in history:
        reqs = h["reeval_requests"]
        print(f"\nRound {h['round']}: {len(reqs)} re-evaluation request(s)")
        for r in reqs:
            print(f"  → {r['target_agent']} re: {r['plan_section']} — {r['question']}")

    # Lifecycle: where did every ever-contested section end up?
    final = result["arbiter"]
    placement: dict[str, str] = {}
    for d in final["needs_decision"]:
        placement[_section_key(d["plan_section"])] = f"needs_decision / {d['disposition']}"
    for c in final["auto_cleared"]:
        placement.setdefault(_section_key(c["plan_section"]), "auto_cleared")

    contested: dict[str, tuple[int, str, str]] = {}
    for h in history:
        for r in h["reeval_requests"]:
            k = _section_key(r["plan_section"])
            contested.setdefault(k, (h["round"], r["target_agent"], r["plan_section"]))

    print("\nContested-item lifecycle:")
    if not contested:
        print("  (none — converged in round 1)")
    for k, (rnd, target, label) in contested.items():
        print(f"  {label}: contested round {rnd} (→ {target}) "
              f"→ {placement.get(k, 'withdrawn / not in final queue')}")


if __name__ == "__main__":
    main()
