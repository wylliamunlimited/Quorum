"""One-shot connection check for W&B Inference.

Confirms three things before we build any real agent:
  1. the API key + base_url authenticate,
  2. the model id is valid,
  3. we can read the response back.

Run:  uv run smoke_test.py
"""

import asyncio

import config
from agents.llm import chat


async def main() -> None:
    print(f"Calling {config.RISK_MODEL} at {config.WANDB_BASE_URL} ...")
    reply = await chat(
        model=config.RISK_MODEL,
        system="You are a terse assistant. Follow instructions exactly.",
        user="Reply with exactly one word: pong",
    )
    print(f"Model replied: {reply!r}")
    print("\n✅ Connection works." if "pong" in reply.lower() else
          "\n⚠️  Got a reply but not the expected word — auth works, check the model output above.")


if __name__ == "__main__":
    asyncio.run(main())
