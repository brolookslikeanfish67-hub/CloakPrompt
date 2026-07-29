"""
CloakPrompt — a local PII masking engine that sits between your app and any
cloud LLM provider. Detects and swaps out PII with placeholders before the
prompt leaves your network, then restores the real values in the response.
"""

from .engine import Masker, MaskResult
from .providers import MaskedOpenAI, MaskedAnthropic, masked_call

__all__ = [
    "Masker",
    "MaskResult",
    "MaskedOpenAI",
    "MaskedAnthropic",
    "masked_call",
]

__version__ = "0.1.0"
