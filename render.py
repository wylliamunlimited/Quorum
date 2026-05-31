"""Render the arbiter's reconciliation into the decision-queue markdown.

This is the product: short. Needs-your-decision items get one line each;
everything the arbiter cleared collapses to a single summary line.
"""

from agents.schemas import ArbiterOutput


def render_decision_queue(arbiter: ArbiterOutput) -> str:
    needs = arbiter["needs_decision"]
    cleared = arbiter["auto_cleared"]
    lines: list[str] = []

    lines.append(f"## Needs your decision ({len(needs)})")
    if not needs:
        lines.append("_Nothing needs you — the panel cleared everything._")
    else:
        for i, d in enumerate(needs, 1):
            lines.append(
                f"{i}. [{d['severity']}] {d['issue']} — {d['why_you']} "
                f"(plan: {d['plan_section']})"
            )

    lines.append("")

    lines.append(f"## Auto-cleared ({len(cleared)})")
    if not cleared:
        lines.append("_Nothing was auto-cleared._")
    else:
        agents_involved = sorted({a for c in cleared for a in c["source_agents"]})
        lines.append(
            f"{len(cleared)} items checked out across {' / '.join(agents_involved)}."
        )

    return "\n".join(lines)
