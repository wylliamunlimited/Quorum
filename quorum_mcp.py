"""Quorum as a local MCP server — lets Claude Code call the panel as a tool.

Claude Code drafts a plan, calls `review_plan`, and gets back the triaged
"Needs your decision" queue (with proposed fixes) — the clarifications to put
to the user before the plan proceeds. Quorum still runs its own W&B agents;
Claude Code is the caller, not the reviewer.

Run directly (stdio):   uv run quorum_mcp.py
Inspect locally:        uv run mcp dev quorum_mcp.py
Register with Claude:   claude mcp add quorum -- uv run --directory <abs-path> quorum_mcp.py
"""

from mcp.server.fastmcp import FastMCP

import config
import tracing
from main import load_expectations
from quorum import run_quorum
from render import render_decision_queue

mcp = FastMCP("quorum")
tracing.init(config.WEAVE_PROJECT)  # keep the Weave trace; no-op if unavailable


@mcp.tool()
async def review_plan(plan: str, expectations_dir: str | None = None) -> str:
    """Review a proposed implementation plan with Quorum's multi-agent panel.

    Run this on a plan BEFORE asking the user to approve it. A panel of
    specialists (risk, edge cases, product-requirement violations) reviews the
    plan and an arbiter reconciles their findings into a short, triaged queue.

    Returns markdown with two sections:
      - "Needs your decision (N)": the items that genuinely need the human —
        present EACH of these to the user as a clarification/decision before
        proceeding. Items may carry a "→ proposed fix:" line you can offer.
      - "Auto-cleared (M)": findings the panel resolved on its own; you do not
        need to raise these.

    Args:
        plan: the proposed plan as markdown text.
        expectations_dir: optional path to a folder of product docs
            (tickets/notes as *.md) to check the plan against. Defaults to
            Quorum's bundled demo docs; pass the target repo's
            ".quorum/expectations" to review against its real requirements.
    """
    try:
        docs = load_expectations(expectations_dir or config.EXPECTATIONS_DIR)
    except Exception as e:
        docs = {}
        print(f"[quorum-mcp] could not load expectations ({e}); reviewing without docs.")

    result = await run_quorum(plan, docs)
    return render_decision_queue(result["arbiter"])


if __name__ == "__main__":
    mcp.run()  # stdio transport
