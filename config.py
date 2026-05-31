"""Central config: model IDs, W&B project slug, paths.

Keeping this in one place so swapping models or pointing at a different
W&B project is a one-line change, not a hunt across the codebase.
"""

import os

from dotenv import load_dotenv

load_dotenv()  # reads .env into the environment if present

# --- W&B Inference (OpenAI-compatible endpoint) ---------------------------
WANDB_ENTITY = "wylliam-cheng-sigma-squared"  # your W&B team/entity slug
WEAVE_PROJECT = f"{WANDB_ENTITY}/quorum"  # used by weave.init(...)
WANDB_BASE_URL = "https://api.inference.wandb.ai/v1"
WANDB_API_KEY = os.environ.get("WANDB_API_KEY")  # set this in your shell / .env

# --- Models ---------------------------------------------------------------
# Llama-3.3-70B for the three narrow specialists; DeepSeek-V3 for the
# reasoning-heavy arbiter (conflict reconciliation).
RISK_MODEL = "meta-llama/Llama-3.3-70B-Instruct"
EDGECASE_MODEL = "meta-llama/Llama-3.3-70B-Instruct"
EXPECTATION_MODEL = "meta-llama/Llama-3.3-70B-Instruct"
ARBITER_MODEL = "deepseek-ai/DeepSeek-V3.1"

# --- Iteration ------------------------------------------------------------
# Max rounds of the confidence loop. The arbiter must commit (no more re-eval
# requests) on the final round; the orchestrator enforces the same cap in code.
MAX_ROUNDS = 3

# --- Input paths ----------------------------------------------------------
PLAN_PATH = "inputs/plan.md"
EXPECTATIONS_DIR = "inputs/expectations"

# --- Expectation source ---------------------------------------------------
# Where the farm-stage gets its requirements: "local" (read EXPECTATIONS_DIR)
# or "jira" (fetch from the Jira-shaped server). Overridable via env / CLI.
EXPECTATIONS_SOURCE = os.environ.get("QUORUM_EXPECTATIONS_SOURCE", "local")
JIRA_BASE_URL = os.environ.get("QUORUM_JIRA_URL", "http://127.0.0.1:8000")
JIRA_PROJECT = os.environ.get("QUORUM_JIRA_PROJECT", "AUTH")
