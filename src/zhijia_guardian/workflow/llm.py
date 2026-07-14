"""Optional, deliberately narrow structured tool-routing interface.

Offline routing remains the default and no API key is required for diagnosis.
"""
from __future__ import annotations

import os
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMMode:
  provider: str
  active: bool
  reason: str


def resolve_llm_mode(provider: str | None = None) -> LLMMode:
  provider = (provider or os.environ.get("LLM_PROVIDER", "none")).lower()
  if provider == "none":
    return LLMMode("none", False, "offline deterministic routing selected")
  if provider == "openai" and os.environ.get("OPENAI_API_KEY"):
    return LLMMode("openai", True, "structured registered-tool routing may be enabled")
  if provider == "deepseek" and os.environ.get("DEEPSEEK_API_KEY"):
    return LLMMode("deepseek", True, "structured registered-tool routing may be enabled")
  return LLMMode("none", False, f"{provider} requested but no supported API key; downgraded to offline deterministic routing")


def select_specialists_with_llm(topics: list[str], candidates: list[str], mode: LLMMode) -> tuple[list[str], str]:
  """One constrained tool call. It sees catalog text only, never messages or oracle."""
  if not mode.active:
    return candidates, mode.reason
  try:
    from openai import OpenAI
    key = os.environ["DEEPSEEK_API_KEY"] if mode.provider == "deepseek" else os.environ["OPENAI_API_KEY"]
    client = OpenAI(api_key=key, base_url="https://api.deepseek.com" if mode.provider == "deepseek" else None)
    tool = {"type": "function", "function": {"name": "select_specialists", "description": "Select only applicable registered diagnostic specialists.",
      "parameters": {"type": "object", "properties": {"agents": {"type": "array", "items": {"type": "string", "enum": candidates}}}, "required": ["agents"], "additionalProperties": False}}}
    model = os.environ.get("LLM_MODEL") or ("deepseek-chat" if mode.provider == "deepseek" else "gpt-4.1-mini")
    response = client.chat.completions.create(model=model, messages=[{"role": "system", "content": "You route diagnostics only. Select tools/agents, do not diagnose causes."},
      {"role": "user", "content": f"Observed topic names only: {topics}. Candidate agents: {candidates}."}], tools=[tool], tool_choice={"type": "function", "function": {"name": "select_specialists"}})
    call = response.choices[0].message.tool_calls[0]
    selected = json.loads(call.function.arguments).get("agents", [])
    selected = [name for name in selected if name in candidates]
    return selected or candidates, f"{mode.provider} structured tool routing applied"
  except Exception as exc:  # Network/provider errors must never block offline diagnosis.
    return candidates, f"{mode.provider} routing failed ({type(exc).__name__}); deterministic routing used"
