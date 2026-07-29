"""
Fast, local, regex/heuristic-based PII detectors.

No network calls, no ML downloads required. Every detector returns a list
of Match(start, end, value, label) tuples found in the input text. Designed
to run in microseconds-to-low-milliseconds on typical prompt sizes so it can
sit inline on the hot path between an app and a cloud LLM provider.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, List


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    value: str
    label: str  # e.g. "EMAIL", "PHONE", "SSN", "CREDITCARD", "APIKEY", "IP", "PERSON", "ADDRESS"


# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

_PHONE_RE = re.compile(
    r"(?<!\d)(\+?\d{1,3}[\s.\-]?)?"
    r"(\(?\d{3}\)?[\s.\-]?)"
    r"\d{3}[\s.\-]?\d{4}(?!\d)"
)

_SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")

_IPV4_RE = re.compile(
    r"(?<!\d)(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?!\d)"
)

# Candidate credit-card-shaped numbers (13-19 digits, optional separators).
# Validated afterwards with the Luhn checksum to cut false positives.
_CC_CANDIDATE_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")

# Common cloud/API secret formats. Extend this list as new provider formats
# become known; order matters only for readability.
_API_KEY_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"),          # Anthropic
    re.compile(r"sk-(?!ant-)[A-Za-z0-9]{20,}"),          # OpenAI legacy
    re.compile(r"sk-proj-[A-Za-z0-9\-_]{20,}"),          # OpenAI project keys
    re.compile(r"AKIA[0-9A-Z]{16}"),                     # AWS access key id
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),               # Google API key
    re.compile(r"ghp_[A-Za-z0-9]{36}"),                  # GitHub PAT
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),        # Slack token
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),  # JWT
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]{20,}=*"),   # generic bearer token
]

_DATE_RE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}/\d{1,2}/\d{2,4}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b"
)

_STREET_SUFFIXES = (
    r"Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Lane|Ln|Drive|Dr|Court|Ct|"
    r"Way|Place|Pl|Terrace|Ter|Circle|Cir|Highway|Hwy|Square|Sq"
)
_ADDRESS_RE = re.compile(
    rf"\d{{1,6}}\s+[A-Za-z0-9.\-]+(?:\s+[A-Za-z0-9.\-]+){{0,3}}\s+(?:{_STREET_SUFFIXES})\.?"
    r"(?:\s*,?\s*(?:Apt|Suite|Ste|Unit|#)\.?\s*\w+)?"
)

# Very small stopword list so obvious sentence-starting capitalized words
# ("The", "This", "Please") aren't flagged as names.
_NAME_STOPWORDS = {
    "The", "This", "That", "These", "Those", "Please", "Thanks", "Thank",
    "Hello", "Hi", "Dear", "Regards", "Sincerely", "Best", "Monday",
    "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December", "I", "AI",
    "API", "URL", "Inc", "LLC", "Ltd",
}
# Two-to-three capitalized-word runs, e.g. "John Smith" / "Mary Jane Watson".
_NAME_RE = re.compile(
    r"\b(?:[A-Z][a-z]+(?:'[A-Za-z]+)?\.?)(?:\s+(?:[A-Z][a-z]+(?:'[A-Za-z]+)?\.?)){1,2}\b"
)


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def find_emails(text: str) -> List[Match]:
    return [Match(m.start(), m.end(), m.group(), "EMAIL") for m in _EMAIL_RE.finditer(text)]


def find_phones(text: str) -> List[Match]:
    out = []
    for m in _PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 10 <= len(digits) <= 15:
            out.append(Match(m.start(), m.end(), m.group(), "PHONE"))
    return out


def find_ssns(text: str) -> List[Match]:
    return [Match(m.start(), m.end(), m.group(), "SSN") for m in _SSN_RE.finditer(text)]


def find_ips(text: str) -> List[Match]:
    return [Match(m.start(), m.end(), m.group(), "IP") for m in _IPV4_RE.finditer(text)]


def find_credit_cards(text: str) -> List[Match]:
    out = []
    for m in _CC_CANDIDATE_RE.finditer(text):
        digits = re.sub(r"[ \-]", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            out.append(Match(m.start(), m.end(), m.group(), "CREDITCARD"))
    return out


def find_api_keys(text: str) -> List[Match]:
    out = []
    for pattern in _API_KEY_PATTERNS:
        for m in pattern.finditer(text):
            out.append(Match(m.start(), m.end(), m.group(), "APIKEY"))
    return out


def find_dates(text: str) -> List[Match]:
    return [Match(m.start(), m.end(), m.group(), "DATE") for m in _DATE_RE.finditer(text)]


def find_addresses(text: str) -> List[Match]:
    return [Match(m.start(), m.end(), m.group(), "ADDRESS") for m in _ADDRESS_RE.finditer(text)]


def find_names(text: str) -> List[Match]:
    out = []
    for m in _NAME_RE.finditer(text):
        first_word = m.group().split()[0].rstrip(".")
        if first_word in _NAME_STOPWORDS:
            continue
        out.append(Match(m.start(), m.end(), m.group(), "PERSON"))
    return out


# Registry used by the engine. Order matters: more specific / higher-risk
# patterns (keys, SSNs, cards) run before the broader NAME heuristic so that
# overlaps resolve in favor of the more precise detector.
DEFAULT_DETECTORS: List[Callable[[str], List[Match]]] = [
    find_api_keys,
    find_ssns,
    find_credit_cards,
    find_emails,
    find_ips,
    find_phones,
    find_addresses,
    find_dates,
    find_names,
]
