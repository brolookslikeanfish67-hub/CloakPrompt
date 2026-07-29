"""
CLI for CloakPrompt.

    cloakprompt mask "Hi I'm Jane Doe, jane@acme.com" > masked.json
    cloakprompt mask "Hi I'm Jane Doe, jane@acme.com" --text-only
    echo '{"masked_text": "...", "mapping": {...}}' | cloakprompt unmask -
"""

from __future__ import annotations

import argparse
import json
import sys

from .engine import Masker


def _cmd_mask(args: argparse.Namespace) -> None:
    masker = Masker()
    result = masker.mask(args.text)
    if args.text_only:
        print(result.masked_text)
    else:
        print(json.dumps(result.to_dict(), indent=2))


def _cmd_unmask(args: argparse.Namespace) -> None:
    payload_raw = sys.stdin.read() if args.json == "-" else args.json
    payload = json.loads(payload_raw)
    masker = Masker()
    print(masker.unmask(payload["masked_text"], payload["mapping"]))


def main() -> None:
    parser = argparse.ArgumentParser(prog="cloakprompt", description="Local PII masking engine.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_mask = sub.add_parser("mask", help="Mask PII in a string.")
    p_mask.add_argument("text", help="Text to mask.")
    p_mask.add_argument("--text-only", action="store_true", help="Print only the masked text.")
    p_mask.set_defaults(func=_cmd_mask)

    p_unmask = sub.add_parser("unmask", help="Restore PII from a {masked_text, mapping} JSON blob.")
    p_unmask.add_argument("json", help="JSON string, or '-' to read from stdin.")
    p_unmask.set_defaults(func=_cmd_unmask)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
