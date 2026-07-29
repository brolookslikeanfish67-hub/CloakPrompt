"""
Example: send a prompt containing PII to Anthropic without Anthropic ever
seeing the real values.

Requires: pip install cloakprompt[anthropic]
Set ANTHROPIC_API_KEY in your environment before running.
"""

from anthropic import Anthropic
from cloakprompt.providers import MaskedAnthropic

client = MaskedAnthropic(Anthropic(), model="claude-sonnet-4-6")

prompt = (
    "Customer John Smith (john.smith@example.com, 555-201-3344) is asking "
    "about order #48213. Draft a support reply."
)

reply = client.chat(prompt)
print(reply)
