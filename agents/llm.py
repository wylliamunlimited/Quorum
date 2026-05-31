"""Shared W&B Inference client + helpers used by every real agent.

One place to build the (async) OpenAI-compatible client and to pull JSON out of
a model response, so each agent file stays focused on its prompt.
"""

import json
import re

import openai

import config

_client: openai.AsyncOpenAI | None = None


def get_client() -> openai.AsyncOpenAI:
    """Lazily build a single shared async client pointed at W&B Inference."""
    global _client
    if _client is None:
        if not config.WANDB_API_KEY:
            raise RuntimeError(
                "WANDB_API_KEY is not set. Copy .env.example to .env and paste "
                "your key (https://wandb.ai/authorize)."
            )
        _client = openai.AsyncOpenAI(
            base_url=config.WANDB_BASE_URL,
            api_key=config.WANDB_API_KEY,
        )
    return _client


async def chat(model: str, system: str, user: str, **kwargs) -> str:
    """Single chat completion; returns the assistant message text."""
    client = get_client()
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        **kwargs,
    )
    return resp.choices[0].message.content or ""


def extract_json(text: str) -> dict:
    """Best-effort parse of a JSON object from a model response.

    Models often wrap JSON in ```json fences or tack an explanation on after
    it. Strip fences, then decode the FIRST complete object starting at the
    first '{' (raw_decode ignores any trailing prose).
    """
    s = text.strip()

    # strip surrounding code fences if present
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)

    # strict parse first (clean responses)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # first complete JSON object; trailing text after it is ignored
    start = s.find("{")
    if start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(s, start)
            return obj
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No JSON object found in model response:\n{text}")


_SEVERITY = {
    "high": "high", "critical": "high", "severe": "high",
    "med": "med", "medium": "med", "moderate": "med",
    "low": "low", "minor": "low", "info": "low",
}


def coerce_agent_output(data: dict) -> dict:
    """Force a model's parsed JSON into the strict AgentOutput shape.

    Tolerates missing keys and severity synonyms (medium->med) so one sloppy
    field never crashes the pipeline. Shared by all three specialists.
    """
    findings_in = data.get("findings", []) if isinstance(data, dict) else []
    findings_out = []
    for f in findings_in:
        if not isinstance(f, dict):
            continue
        sev = str(f.get("severity", "med")).lower().strip()
        findings_out.append({
            "severity": _SEVERITY.get(sev, "med"),
            "issue": str(f.get("issue", "")).strip(),
            "plan_section": str(f.get("plan_section", "")).strip(),
            "why": str(f.get("why", "")).strip(),
        })
    return {"findings": findings_out}
