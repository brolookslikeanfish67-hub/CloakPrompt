# 🕶️ CloakPrompt

**A local PII masking engine that sits between your app and any cloud LLM provider.**

Cloud models like GPT-4o and Claude are cheap and powerful, but sending them
customer names, emails, SSNs, credit cards, or API keys can violate GDPR,
HIPAA, PCI-DSS, or your own data policy. CloakPrompt intercepts the prompt,
strips out PII locally (no network calls, no data ever leaves your machine
during detection), swaps it for stable placeholders like `[PERSON_1]` and
`[EMAIL_1]`, sends the sanitized prompt to the cloud model, and swaps the
real values back into the response — all transparently.

```
 Your app                CloakPrompt (local)              Cloud LLM
┌─────────┐   prompt    ┌──────────────────┐  masked   ┌───────────┐
│  "Jane  │ ──────────► │  detect + mask   │ ────────► │  OpenAI / │
│  Doe... │             │  PII locally     │  prompt   │ Anthropic │
└─────────┘             └──────────────────┘           └───────────┘
     ▲                          │                            │
     │        real reply        │        masked reply        │
     └────────── unmask ◄───────┴─────────────────────────────┘
```

No real name, email, phone number, SSN, credit card, IP address, physical
address, or API key ever crosses the wire to the model provider.

## Why it matters

- **Legally safer cloud AI.** Use GPT-4o, Claude, or any hosted model on
  sensitive data without it ever seeing the raw PII.
- **Zero network dependency for detection.** All matching runs locally
  with regex + checksum validation (e.g. Luhn for card numbers) — no PII
  is sent anywhere just to be classified.
- **Drop-in.** Wrap your existing OpenAI/Anthropic client in one line, or
  use the generic `masked_call()` helper for any HTTP-based provider.
- **Consistent across a conversation.** The same person/email/card gets
  the same placeholder every time within a session, so multi-turn context
  still makes sense to the model.

## What it detects

| Type | Label | Method |
|---|---|---|
| Names | `PERSON` | Capitalization heuristic + stopword filtering |
| Emails | `EMAIL` | RFC-ish regex |
| Phone numbers | `PHONE` | Regex + digit-count validation |
| Social Security Numbers | `SSN` | `###-##-####` pattern |
| Credit card numbers | `CREDITCARD` | Candidate regex + **Luhn checksum** validation |
| IP addresses | `IP` | IPv4 regex |
| API keys / secrets | `APIKEY` | Known formats: OpenAI, Anthropic, AWS, GCP, GitHub, Slack, JWT, generic bearer tokens |
| Street addresses | `ADDRESS` | Number + street-suffix heuristic |
| Dates | `DATE` | ISO, US, and long-form date patterns |

This is a fast, local, deterministic first line of defense — it is not a
substitute for a full enterprise DLP/NER pipeline on extremely high-stakes
data, but it's dependency-free and runs in milliseconds. See
[Limitations](#limitations) below.

## Install

**Python**

```bash
pip install cloakprompt
# or, from source:
pip install -e .
```

**JavaScript / Node**

```bash
cd js && npm install
```

## Quick start (Python)

```python
from cloakprompt import Masker

masker = Masker()
result = masker.mask(
    "Hi, I'm Jane Doe. My email is jane@acme.com and my card is 4111 1111 1111 1111."
)
print(result.masked_text)
# "Hi, I'm [PERSON_1]. My email is [EMAIL_1] and my card is [CREDITCARD_1]."

# ... send result.masked_text to your cloud LLM provider ...

reply_from_llm = "Thanks [PERSON_1], we'll email your receipt to [EMAIL_1]."
print(masker.unmask(reply_from_llm, result.mapping))
# "Thanks Jane Doe, we'll email your receipt to jane@acme.com."
```

### One-line wrap for OpenAI

```python
from openai import OpenAI
from cloakprompt.providers import MaskedOpenAI

client = MaskedOpenAI(OpenAI(), model="gpt-4o-mini")
print(client.chat("My name is Jane Doe, jane@acme.com — draft a refund email."))
```

### One-line wrap for Anthropic

```python
from anthropic import Anthropic
from cloakprompt.providers import MaskedAnthropic

client = MaskedAnthropic(Anthropic(), model="claude-sonnet-4-6")
print(client.chat("Customer John Smith (555-201-3344) needs order status."))
```

### Any provider

```python
from cloakprompt.providers import masked_call

def call_my_gateway(masked_text: str) -> str:
    ...  # your HTTP call to any LLM API

result = masked_call("Maria Garcia's SSN is 123-45-6789.", call_my_gateway)
print(result["reply"])
```

More runnable examples in [`examples/`](examples/).

### CLI

```bash
cloakprompt mask "Call Jane Doe at 555-123-4567" --text-only
# Call [PERSON_1] at [PHONE_1]

cloakprompt mask "Call Jane Doe at 555-123-4567" > out.json
cat out.json | cloakprompt unmask -
# Call Jane Doe at 555-123-4567
```

## Quick start (JavaScript)

```js
const { Masker } = require("cloakprompt");

const masker = new Masker();
const { maskedText, mapping } = masker.mask(
  "Jane Doe <jane@acme.com>, card 4111 1111 1111 1111"
);
console.log(maskedText); // "[PERSON_1] <[EMAIL_1]>, card [CREDITCARD_1]"

// ... send maskedText to your cloud LLM provider ...

const restored = masker.unmask("Thanks [PERSON_1]!", mapping);
console.log(restored); // "Thanks Jane Doe!"
```

## Session-consistent masking across a conversation

```python
masker = Masker()
r1 = masker.mask("Jane Doe emailed jane@acme.com about her order.")
r2 = masker.mask("Jane Doe followed up again today.", session_mapping=r1.mapping)
# "Jane Doe" is [PERSON_1] in both r1 and r2 — the model sees a consistent
# identity across turns without ever learning who it actually is.
```

## How masking works internally

1. Run every detector (email, phone, SSN, credit card + Luhn, API key,
   IP, address, date, name) over the input text.
2. Resolve overlapping matches, preferring the earliest and longest match
   (so a detected API key inside a longer string isn't double-masked by
   the name heuristic, etc).
3. Assign each unique value a stable placeholder (`[LABEL_N]`), reusing
   placeholders for values already seen in the current session.
4. Rebuild the string with placeholders swapping in for real values.
5. After the cloud model responds, swap any placeholders that appear in
   its reply back to the real value using the same mapping — the mapping
   never leaves your process.

## Limitations

- The name detector is a fast heuristic (capitalized-word-sequence +
  stopword list), not a trained NER model — it will miss single-word
  names, unusual capitalization, and non-Western name formats, and can
  occasionally over-flag capitalized phrases. For higher-recall name
  detection, swap in your own detector via the `detectors=[...]` argument
  to `Masker()`.
- The mapping (placeholder → real value) lives in memory for the
  duration of your process. Persisting it (e.g. to a database) is your
  responsibility if you need it across restarts — treat that store with
  the same sensitivity as the original data.
- This library reduces what leaves your network; it does not itself
  encrypt, log, or audit anything, and it isn't a certified compliance
  product. Validate detector coverage against your own regulatory
  requirements before relying on it for GDPR/HIPAA/PCI-DSS compliance.

## Contributing

Detector patterns for more PII types, additional API key formats, and a
higher-recall NER-based name detector (optional dependency) are all
welcome. Open a PR or issue.

## License

MIT — see [LICENSE](LICENSE).
