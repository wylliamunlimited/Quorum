"""Jira fetch adapter — the farm-stage's data source when source = "jira".

Pulls issues from a Jira-shaped API (the dummy server, or real Jira) and returns
them in the same {name: text} shape the Requirement Farmer already consumes, so
nothing downstream changes. Fails soft (returns {}) so a missing server never
crashes a review.
"""

import httpx


def _issue_to_text(issue: dict) -> str:
    """Flatten a Jira issue into the plain text the farmer distills."""
    f = issue.get("fields", {}) or {}
    summary = f.get("summary", "")
    description = f.get("description", "")
    issuetype = (f.get("issuetype") or {}).get("name", "")
    priority = (f.get("priority") or {}).get("name", "")
    status = (f.get("status") or {}).get("name", "")
    header = f"{issue.get('key', '')} — {summary}"
    meta = f"Type: {issuetype} | Priority: {priority} | Status: {status}"
    return f"{header}\n{meta}\n\n{description}".strip()


async def fetch_jira_expectations(
    base_url: str, project: str | None = None
) -> dict[str, str]:
    """Fetch issues from `{base_url}/rest/api/3/search` and return {key: text}."""
    params = {}
    if project:
        params["jql"] = f"project={project}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{base_url}/rest/api/3/search", params=params)
            resp.raise_for_status()
            issues = resp.json().get("issues", [])
    except Exception as e:  # server down / bad response — don't kill the review
        print(f"[jira] fetch failed ({e}); returning no requirements.")
        return {}

    return {i.get("key", f"ISSUE-{n}"): _issue_to_text(i) for n, i in enumerate(issues)}
