"""Shared data shapes — the contract between agents and the arbiter.

These are TypedDicts (zero runtime cost) so the JSON shapes are documented in
one place. The three specialists emit `AgentOutput`; the arbiter consumes three
of those and emits `ArbiterOutput`.
"""

from typing import Literal, TypedDict

Severity = Literal["high", "med", "low"]


class Finding(TypedDict):
    """One issue flagged by a specialist agent."""
    severity: Severity
    issue: str          # one-line description
    plan_section: str   # e.g. "step 2" — the join key the arbiter aligns on
    why: str            # why it matters, in the agent's own narrow lens


class AgentOutput(TypedDict):
    findings: list[Finding]


class Decision(TypedDict):
    """A finding the arbiter decided the human must see."""
    severity: Severity
    issue: str
    why_you: str               # why THIS needs a human (not just why it matters)
    plan_section: str
    source_agents: list[str]   # which agent(s) raised it
    disposition: Literal["keep", "escalate"]


class Cleared(TypedDict):
    """A finding the arbiter resolved on the human's behalf."""
    issue: str
    plan_section: str
    source_agents: list[str]
    reason: str                # why it was safe to clear


class ArbiterOutput(TypedDict):
    needs_decision: list[Decision]
    auto_cleared: list[Cleared]
