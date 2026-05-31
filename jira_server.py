"""Dummy Jira server — returns Jira-REST-shaped issue data for the demo.

Serves a fixed set of issues (jira_fixtures.json) at the real Jira search/issue
endpoints, so Quorum's fetch adapter can pull "requirements" from an API instead
of local files. Not real Jira — just the shape.

Run:  uv run jira_server.py            # http://127.0.0.1:8000
Try:  curl 'http://127.0.0.1:8000/rest/api/3/search?jql=project=AUTH'
"""

import json
import re
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

_FIXTURES = json.loads(
    (Path(__file__).parent / "jira_fixtures.json").read_text(encoding="utf-8")
)
_ISSUES = _FIXTURES["issues"]


def _project_of(key: str) -> str:
    return key.split("-", 1)[0]


async def search(request: Request) -> JSONResponse:
    """GET /rest/api/3/search?jql=project=<KEY> — Jira-shaped search response."""
    jql = request.query_params.get("jql", "")
    m = re.search(r"project\s*=\s*([A-Za-z0-9_]+)", jql)
    project = m.group(1).upper() if m else None

    issues = [i for i in _ISSUES if not project or _project_of(i["key"]).upper() == project]
    return JSONResponse({
        "startAt": 0,
        "maxResults": len(issues),
        "total": len(issues),
        "issues": issues,
    })


async def issue(request: Request) -> JSONResponse:
    """GET /rest/api/3/issue/{key} — a single issue."""
    key = request.path_params["key"]
    for i in _ISSUES:
        if i["key"].upper() == key.upper():
            return JSONResponse(i)
    return JSONResponse({"errorMessages": [f"Issue does not exist: {key}"]}, status_code=404)


app = Starlette(routes=[
    Route("/rest/api/3/search", search),
    Route("/rest/api/3/issue/{key}", issue),
])


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
