"""
Example: send a prompt containing PII to OpenAI without OpenAI ever seeing
the real values.

Requires: pip install cloakprompt[openai]
Set OPENAI_API_KEY in your environment before running.
"""

from openai import OpenAI
from cloakprompt.providers import MaskedOpenAI

client = MaskedOpenAI(OpenAI(), model="gpt-4o-mini")

prompt = (
    "Hi, my name is Jane Doe. My email is jane.doe@acme.com and my card "
    "number is 4111 1111 1111 1111. Can you write a polite refund email "
    "using my details?"
)

# OpenAI only ever sees placeholders like [PERSON_1], [EMAIL_1], [CREDITCARD_1].
reply = client.chat(prompt)
print(reply)  # Real name/email/card are restored locally in the final reply.
