"""
Example: use masked_call() with ANY provider — you supply a plain
`call_fn(masked_text) -> response_text` function, CloakPrompt handles the
masking and unmasking around it. Useful for providers without a dedicated
wrapper, internal proxies, or self-hosted gateways.
"""

import requests
from cloakprompt.providers import masked_call


def call_my_llm_gateway(masked_text: str) -> str:
    resp = requests.post(
        "https://my-llm-gateway.internal/v1/complete",
        json={"prompt": masked_text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["text"]


result = masked_call(
    "Please summarize this ticket from customer Maria Garcia (maria@example.com).",
    call_my_llm_gateway,
)

print(result["reply"])          # PII restored
print(result["masked_prompt"])  # what actually left your network
