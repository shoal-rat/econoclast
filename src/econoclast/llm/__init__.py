"""The native-LLM layer: one backend, driven through Claude Code or Codex."""

from econoclast.llm.backend import Backend, detect_backend
from econoclast.llm.base import (
    LLMError,
    LLMProvider,
    LLMResponse,
    Message,
    Usage,
    extract_json,
)

__all__ = [
    "Backend",
    "LLMError",
    "LLMProvider",
    "LLMResponse",
    "Message",
    "Usage",
    "detect_backend",
    "extract_json",
]
