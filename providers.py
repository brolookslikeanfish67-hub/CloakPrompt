"""
Drop-in wrappers that mask outgoing prompts and unmask incoming responses
around a real cloud LLM call. CloakPrompt never sends the API key or your
data anywhere itself — it just masks locally before you hand the text to
your existing OpenAI/Anthropic client, and unmasks the reply.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from .engine import Masker


def masked_call(
    text: str,
    call_fn: Callable[[str], str],
    masker: Optional[Masker] = None,
    session_mapping: Optional[Dict[str, str]] = None,
) -> Dict[str, object]:
    """
    Generic helper: mask `text`, pass the masked version to `call_fn`
    (any function that takes a string prompt and returns a string
    response — e.g. a lambda wrapping your OpenAI/Anthropic call),
    then unmask the result.

    Returns {"reply": <unmasked reply>, "masked_prompt": ..., "mapping": ...}
    """
    masker = masker or Masker()
    result = masker.mask(text, session_mapping=session_mapping)
    raw_reply = call_fn(result.masked_text)
    reply = masker.unmask(raw_reply, result.mapping)
    return {"reply": reply, "masked_prompt": result.masked_text, "mapping": result.mapping}


class MaskedOpenAI:
    """
    Wraps an existing `openai.OpenAI()` client so chat messages are masked
    before they leave your network and the reply is unmasked locally.

        from openai import OpenAI
        from cloakprompt.providers import MaskedOpenAI

        client = MaskedOpenAI(OpenAI(api_key="..."))
        reply = client.chat("My name is Jane Doe, email jane@acme.com...")
    """

    def __init__(self, client, model: str = "gpt-4o-mini", masker: Optional[Masker] = None):
        self.client = client
        self.model = model
        self.masker = masker or Masker()
        self._session_mapping: Dict[str, str] = {}

    def chat(self, user_message: str, keep_session: bool = True, **kwargs) -> str:
        mapping = self._session_mapping if keep_session else None
        result = self.masker.mask(user_message, session_mapping=mapping)
        if keep_session:
            self._session_mapping = result.mapping

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": result.masked_text}],
            **kwargs,
        )
        raw_reply = response.choices[0].message.content or ""
        return self.masker.unmask(raw_reply, result.mapping)


class MaskedAnthropic:
    """
    Wraps an existing `anthropic.Anthropic()` client the same way.

        from anthropic import Anthropic
        from cloakprompt.providers import MaskedAnthropic

        client = MaskedAnthropic(Anthropic(api_key="..."))
        reply = client.chat("Call me at 555-123-4567 about my order.")
    """

    def __init__(self, client, model: str = "claude-sonnet-4-6", masker: Optional[Masker] = None):
        self.client = client
        self.model = model
        self.masker = masker or Masker()
        self._session_mapping: Dict[str, str] = {}

    def chat(self, user_message: str, max_tokens: int = 1024, keep_session: bool = True, **kwargs) -> str:
        mapping = self._session_mapping if keep_session else None
        result = self.masker.mask(user_message, session_mapping=mapping)
        if keep_session:
            self._session_mapping = result.mapping

        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": result.masked_text}],
            **kwargs,
        )
        text_blocks: List[str] = [b.text for b in response.content if getattr(b, "type", "") == "text"]
        raw_reply = "\n".join(text_blocks)
        return self.masker.unmask(raw_reply, result.mapping)
