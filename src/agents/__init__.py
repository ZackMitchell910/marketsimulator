# market_twin/agents/__init__.py
from .base import BaseAgent
from .llm import LLMAgent

try:
    from .fund import FundAgent
except Exception:
    FundAgent = None

try:
    from .retail import RetailAgent  # stub is fine if you added it earlier
except Exception:
    RetailAgent = None

__all__ = ["BaseAgent", "LLMAgent", "FundAgent", "RetailAgent"]
