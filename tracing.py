"""Optional Weave tracing.

The import is guarded so the whole pipeline still runs if weave isn't installed
or W&B is unreachable. `op` is a decorator that becomes a no-op in that case;
`init` is called once from main().
"""

try:
    import weave
    _AVAILABLE = True
except ImportError:  # weave optional — pipeline must run without it
    weave = None
    _AVAILABLE = False


def init(project: str) -> None:
    """Start Weave tracing for `project` (e.g. 'wylliam-cheng/quorum')."""
    if not _AVAILABLE:
        print("[weave] not installed — running without tracing.")
        return
    try:
        weave.init(project)
        print(f"[weave] tracing to {project}")
    except Exception as e:  # bad auth / offline — don't kill the run
        print(f"[weave] init failed ({e}) — running without tracing.")


def op(fn):
    """Decorate an agent function as a Weave op (no-op if weave is absent)."""
    if _AVAILABLE:
        return weave.op()(fn)
    return fn
