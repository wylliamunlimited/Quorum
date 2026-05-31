"""Shared data shapes — the contract between agents and the arbiter.

These are TypedDicts (zero runtime cost) so the JSON shapes are documented in
one place. The three specialists emit `AgentOutput`; the arbiter consumes three
of those and emits `ArbiterOutput`.
"""

from typing import Literal, NotRequired, TypedDict

Severity = Literal["high", "med", "low"]
AgentName = Literal["Risk", "EdgeCase", "Expectation"]


class Requirement(TypedDict):
    """One verified product requirement farmed from the docs (plan-independent).

    The "what do people want" artifact: the Expectation farm-stage extracts these,
    and its act-stage judges the plan against them, citing the source.
    """
    source: str         # e.g. "AUTH-101" or "meeting-notes"
    requirement: str    # the verified want, in plain terms


Requirements = list[Requirement]


class Finding(TypedDict):
    """One issue flagged by a specialist agent."""
    severity: Severity
    issue: str          # one-line description
    plan_section: str   # e.g. "step 2" — the join key the arbiter aligns on
    why: str            # why it matters, in the agent's own narrow lens
    # A concrete suggested change (Expectation act-stage only, for now).
    proposed_fix: NotRequired[str]


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
    # Stitched in by the orchestrator from the originating Expectation finding.
    proposed_fix: NotRequired[str]


class Cleared(TypedDict):
    """A finding the arbiter resolved on the human's behalf."""
    issue: str
    plan_section: str
    source_agents: list[str]
    reason: str                # why it was safe to clear
    # For a cleared DESTRUCTIVE op: the specific doc/note that authorizes it.
    # The orchestrator escalates destructive clears whose citation doesn't verify.
    authorized_by: NotRequired[str]


class ReevalRequest(TypedDict):
    """The arbiter routing a contested item back to ONE specialist for a second
    look. The specialists never see each other directly — only what the arbiter
    routes here. The presence of any request means a finding is still contested;
    an empty/absent `reeval_requests` means the triage has converged.
    """
    target_agent: AgentName    # who is best placed to resolve it
    plan_section: str          # the contested item's join key
    question: str              # the arbiter's specific uncertainty, one line
    context: str               # cross-context to route (another agent's finding)


class ArbiterOutput(TypedDict):
    needs_decision: list[Decision]
    auto_cleared: list[Cleared]
    # Absent/empty == converged. Drives the bounded re-evaluation loop.
    reeval_requests: NotRequired[list[ReevalRequest]]
