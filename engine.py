"""
CloakPrompt engine: mask PII before it leaves your network, unmask it in the
response that comes back — without the cloud model ever seeing real values.

    from cloakprompt import Masker

    masker = Masker()
    result = masker.mask("Hi, I'm Jane Doe, email jane@acme.com, card 4111 1111 1111 1111")
    result.masked_text
    # "Hi, I'm [PERSON_1], email [EMAIL_1], card [CREDITCARD_1]"

    # ... send result.masked_text to OpenAI/Anthropic/etc ...

    real_reply = masker.unmask(llm_reply_text, result.mapping)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .detectors import DEFAULT_DETECTORS, Match

PLACEHOLDER_RE = re.compile(r"\[([A-Z]+)_(\d+)\]")


@dataclass
class MaskResult:
    masked_text: str
    mapping: Dict[str, str]           # placeholder -> original value
    matches: List[Match] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"masked_text": self.masked_text, "mapping": self.mapping}


class Masker:
    """
    Detects PII in text, replaces it with stable placeholders like
    [PERSON_1], [EMAIL_1], [CREDITCARD_1], and can reverse the process on
    text that comes back (e.g. an LLM response that echoes a placeholder).

    A single Masker instance can be reused across many mask() calls; each
    call gets its own independent mapping unless you pass session_mapping
    to keep numbering consistent across multiple prompts in one
    conversation (so "Jane Doe" is always [PERSON_1] within a session).
    """

    def __init__(
        self,
        detectors: Optional[List[Callable[[str], List[Match]]]] = None,
        placeholder_format: str = "[{label}_{n}]",
    ):
        self.detectors = detectors if detectors is not None else DEFAULT_DETECTORS
        self.placeholder_format = placeholder_format

    def mask(self, text: str, session_mapping: Optional[Dict[str, str]] = None) -> MaskResult:
        """
        Mask all detected PII in `text`.

        If `session_mapping` (placeholder -> original) is supplied, reuses
        its placeholders for values already seen so the same person/email/
        etc. gets the same placeholder across multiple calls in a
        conversation, and continues numbering new values from where it
        left off.
        """
        all_matches: List[Match] = []
        for detector in self.detectors:
            all_matches.extend(detector(text))

        # Resolve overlaps: keep the earliest-starting match; among matches
        # that start at the same point, keep the longest one.
        all_matches.sort(key=lambda m: (m.start, -(m.end - m.start)))
        kept: List[Match] = []
        last_end = -1
        for m in all_matches:
            if m.start >= last_end:
                kept.append(m)
                last_end = m.end

        mapping: Dict[str, str] = dict(session_mapping or {})
        value_to_placeholder: Dict[str, str] = {v: k for k, v in mapping.items()}
        counters: Dict[str, int] = {}
        for placeholder in mapping:
            pm = PLACEHOLDER_RE.fullmatch(placeholder)
            if pm:
                label, n = pm.group(1), int(pm.group(2))
                counters[label] = max(counters.get(label, 0), n)

        # Build the masked string back-to-front so earlier offsets stay valid.
        out_parts = []
        cursor = len(text)
        for m in reversed(kept):
            out_parts.append(text[m.end:cursor])
            if m.value in value_to_placeholder:
                placeholder = value_to_placeholder[m.value]
            else:
                counters[m.label] = counters.get(m.label, 0) + 1
                placeholder = self.placeholder_format.format(label=m.label, n=counters[m.label])
                mapping[placeholder] = m.value
                value_to_placeholder[m.value] = placeholder
            out_parts.append(placeholder)
            cursor = m.start
        out_parts.append(text[:cursor])
        masked_text = "".join(reversed(out_parts))

        return MaskResult(masked_text=masked_text, mapping=mapping, matches=kept)

    def unmask(self, text: str, mapping: Dict[str, str]) -> str:
        """Replace every placeholder in `text` with its original value."""
        def _replace(m: re.Match) -> str:
            placeholder = m.group(0)
            return mapping.get(placeholder, placeholder)

        return PLACEHOLDER_RE.sub(_replace, text)
