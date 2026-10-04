"""Model, MCP, and limit configuration for the Campus Customs agent team."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

BACKEND_DIR = Path(__file__).resolve().parent
HW5_ROOT = BACKEND_DIR.parent
COURSE_ROOT = HW5_ROOT.parent

# PORTKEY_API_KEY: a .env in this repo's root (see .env.example) wins; otherwise the
# AI Foundations course-root .env one folder up is used.
load_dotenv(HW5_ROOT / ".env")
load_dotenv(COURSE_ROOT / ".env")

PROMPTS_DIR = BACKEND_DIR / "prompts"
AUDIT_PATH = HW5_ROOT / "output" / "audit_trail.json"
MCP_SERVER_PATH = HW5_ROOT / "mcp_server" / "server.py"
_VENV_PYTHON = HW5_ROOT / ".venv" / "bin" / "python"
MCP_PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else "python3"

# Every agent uses this one model. Not overridable by env on purpose.
MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
PORTKEY_PROVIDER = "openai"

# ---------------------------------------------------------------------------
# Token / loop / delegation limits
# ---------------------------------------------------------------------------
# Sized at ~1.5x the peak observed across six successful runs of tickets 101-103
# (peak: 61.2k tokens, 17 requests, 24 tool calls, 4 delegations, depth 2, 30 s/delegation).
MAX_DELEGATION_DEPTH = 2          # boss (0) -> specialist (1) -> specialist (2)
MAX_DELEGATIONS_PER_TICKET = 6    # total delegate() calls that actually start a sub-agent
DELEGATION_TIMEOUT_SECONDS = 90   # wall clock for one delegated sub-agent run
AGENT_RETRIES = 2                 # tool-call / output-validation retries per agent run
MAX_OUTPUT_TOKENS_PER_RESPONSE = 4_000  # per model response, reasoning included

# One shared usage counter covers the whole ticket (boss + all sub-agents).
TICKET_USAGE_LIMITS = UsageLimits(
    request_limit=25,
    tool_calls_limit=35,
    total_tokens_limit=90_000,
    output_tokens_limit=14_000,
)

# Sub-agents stop earlier on the same shared counter, so a runaway delegation
# fails back to its caller and the boss keeps a reserve to write its decision.
BOSS_RESERVE = {"requests": 4, "tool_calls": 4, "total_tokens": 15_000, "output_tokens": 3_000}
SUBAGENT_USAGE_LIMITS = UsageLimits(
    request_limit=TICKET_USAGE_LIMITS.request_limit - BOSS_RESERVE["requests"],
    tool_calls_limit=TICKET_USAGE_LIMITS.tool_calls_limit - BOSS_RESERVE["tool_calls"],
    total_tokens_limit=TICKET_USAGE_LIMITS.total_tokens_limit - BOSS_RESERVE["total_tokens"],
    output_tokens_limit=TICKET_USAGE_LIMITS.output_tokens_limit - BOSS_RESERVE["output_tokens"],
)


def require_api_key() -> str:
    key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not key:
        raise RuntimeError(f"PORTKEY_API_KEY is not set in {COURSE_ROOT / '.env'}")
    return key


def build_model() -> OpenAIResponsesModel:
    if MODEL_NAME != "gpt-6-luna":
        raise RuntimeError("Every Campus Customs agent must use gpt-6-luna through Portkey.")
    client = AsyncOpenAI(
        api_key=require_api_key(),
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-provider": PORTKEY_PROVIDER},
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
