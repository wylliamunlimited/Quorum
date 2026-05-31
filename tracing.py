"""Optional Weave tracing.

The import is guarded so the whole pipeline still runs if weave isn't installed
or W&B is unreachable. `op` is a decorator that becomes a no-op in that case;
`init` is called once from main().

Status messages go to stderr so stdout stays clean (just the decision queue) —
the plan-review hook captures stdout verbatim.
"""

import sys

try:
    import weave
    _AVAILABLE = True
except ImportError:  # weave optional — pipeline must run without it
    weave = None
    _AVAILABLE = False


def init(project: str) -> None:
    """Start Weave tracing for `project` (e.g. 'wylliam-cheng/quorum')."""
    if not _AVAILABLE:
        print("[weave] not installed — running without tracing.", file=sys.stderr)
        return
    try:
        weave.init(project)
        print(f"[weave] tracing to {project}", file=sys.stderr)
    except Exception as e:  # bad auth / offline — don't kill the run
        print(f"[weave] init failed ({e}) — running without tracing.", file=sys.stderr)


def op(fn):
    """Decorate an agent function as a Weave op (no-op if weave is absent)."""
    if _AVAILABLE:
        return weave.op()(fn)
    return fn
