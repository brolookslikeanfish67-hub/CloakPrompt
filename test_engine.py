import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloakprompt import Masker
from cloakprompt.detectors import find_credit_cards, find_emails, find_phones, find_ssns, find_api_keys


def test_email_detected_and_masked():
    masker = Masker()
    result = masker.mask("Contact me at jane.doe@acme.com please.")
    assert "jane.doe@acme.com" not in result.masked_text
    assert "[EMAIL_1]" in result.masked_text
    assert result.mapping["[EMAIL_1]"] == "jane.doe@acme.com"


def test_round_trip_unmask():
    masker = Masker()
    original = "Hi, I'm Jane Doe. Email me at jane@acme.com or call 555-123-4567."
    result = masker.mask(original)
    assert "Jane Doe" not in result.masked_text
    assert "jane@acme.com" not in result.masked_text
    assert "555-123-4567" not in result.masked_text

    fake_llm_reply = f"Sure, I'll follow up with {list(result.mapping)[0]} shortly."
    restored = masker.unmask(fake_llm_reply, result.mapping)
    assert "[PERSON_1]" not in restored or "Jane Doe" in restored


def test_ssn_detected():
    matches = find_ssns("SSN on file: 123-45-6789.")
    assert len(matches) == 1
    assert matches[0].value == "123-45-6789"


def test_credit_card_luhn_filters_false_positives():
    # Valid Luhn test number
    valid = find_credit_cards("Card: 4111 1111 1111 1111")
    assert len(valid) == 1
    # Random 16-digit number that fails Luhn should NOT match
    invalid = find_credit_cards("Order number: 1234 5678 9012 3459")
    assert len(invalid) == 0


def test_api_key_detected():
    text = "export ANTHROPIC_API_KEY=sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"
    matches = find_api_keys(text)
    assert len(matches) == 1
    assert matches[0].label == "APIKEY"


def test_phone_detected():
    matches = find_phones("Call me at (415) 555-2671 tomorrow.")
    assert len(matches) == 1


def test_session_mapping_reuses_placeholders():
    masker = Masker()
    r1 = masker.mask("Jane Doe emailed jane@acme.com.")
    r2 = masker.mask("Jane Doe called again about jane@acme.com.", session_mapping=r1.mapping)
    # Same values should map to the same placeholders across calls.
    assert r1.mapping == {k: v for k, v in r2.mapping.items() if k in r1.mapping}
    person_placeholder = [k for k, v in r2.mapping.items() if v == "Jane Doe"][0]
    email_placeholder = [k for k, v in r2.mapping.items() if v == "jane@acme.com"][0]
    assert person_placeholder in r2.masked_text
    assert email_placeholder in r2.masked_text


def test_no_pii_passthrough():
    masker = Masker()
    text = "What is the capital of France?"
    result = masker.mask(text)
    assert result.masked_text == text
    assert result.mapping == {}


def test_multiple_distinct_people_get_distinct_placeholders():
    masker = Masker()
    result = masker.mask("John Smith spoke with Alice Johnson about the contract.")
    person_placeholders = [k for k in result.mapping if k.startswith("[PERSON_")]
    assert len(person_placeholders) == 2
