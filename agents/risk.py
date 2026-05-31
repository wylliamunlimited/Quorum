"""Risk agent — finds destructive / irreversible operations. Nothing else.

Step 3: real W&B Inference call (Llama-3.3). Signature and return shape are
identical to the old stub, so quorum.py / render.py / main.py are untouched.
"""

import config
from agents.llm import REEVAL_INSTRUCTION, chat, coerce_agent_output, extract_json
from agents.schemas import AgentOutput
from tracing import op

AGENT_NAME = "Risk"

# The 5-part prompt:
#   1) one-line role  2) hard exclusions  3) labeled input (in the user msg)
#   4) JSON-only + inline example  5) anti-confabulation clause
SYSTEM_PROMPT = """\
You are the RISK reviewer on a panel that reviews a software change plan before \
a human approves it. Your single job: find DESTRUCTIVE or IRREVERSIBLE \
operations in the plan.

Things that count (non-exhaustive):
- Deleting or dropping data, tables, columns, files, branches.
- Schema migrations that lose or overwrite existing data.
- Force-pushing or rewriting shared git history.
- Truncating/overwriting data, wiping state, irreversible deploys.
- Removing dependencies or services other things rely on.
The test is simple: if this step went wrong, could it be easily undone? If not, \
it's a risk.

You do NOT do the other reviewers' jobs:
- You do NOT evaluate unhandled inputs, edge cases, or failure modes — another \
agent owns that.
- You do NOT judge whether the plan matches product requirements or user \
expectations — another agent owns that.
- You do NOT comment on style, performance, naming, or general best practices.
If a concern is not a destructive/irreversible operation, leave it out.

Output ONLY a JSON object in exactly this shape, nothing before or after:
{"findings":[{"severity":"high|med|low","issue":"<one line>","plan_section":"step <N>","why":"<one sentence: why it is destructive/irreversible>"}]}

If the plan contains NO destructive or irreversible operations, return \
{"findings":[]}. Do not invent issues to seem useful. Every finding must point \
to a specific operation that actually appears in the plan.""" + REEVAL_INSTRUCTION


@op
async def run_risk_agent(plan: str, context: str | None = None) -> AgentOutput:
    user = f"PLAN:\n{plan}"
    if context:
        user += f"\n\n{context}"
    raw = await chat(config.RISK_MODEL, SYSTEM_PROMPT, user, temperature=0)
    try:
        return coerce_agent_output(extract_json(raw))
    except Exception as e:  # never let one bad parse kill the run
        print(f"[Risk] could not parse model output ({e}); returning no findings.")
        return {"findings": []}
