# contacts.py — customer phone-number validation (Phase 5B-1)
#
# One place for the rule so stock sales, treatments and customer updates can
# never disagree. Deliberately permissive about FORMAT (Nigerian numbers in
# any common style, and international numbers) but strict that a number must
# be present and look like a real phone number — blank and whitespace-only
# values are always rejected.
#
#   "0801 234 5678" -> "08012345678"
#   "+234 801 234 5678" -> "+2348012345678"
#   "", "   ", "abc", "12345" -> rejected

import re

PHONE_REQUIRED_MSG = "Customer phone number is required for credit. Please enter it."
PHONE_INVALID_MSG = "That phone number doesn't look right. Use 7 to 15 digits, for example 08012345678."

_STRIP = re.compile(r"[\s\-\.\(\)]")
_VALID = re.compile(r"^\+?\d{7,15}$")


def normalize_phone(phone):
    """Returns (clean_phone, error_message). Exactly one of them is None."""
    raw = (phone or "").strip()
    if not raw:
        return None, PHONE_REQUIRED_MSG
    cleaned = _STRIP.sub("", raw)
    if not _VALID.match(cleaned):
        return None, PHONE_INVALID_MSG
    return cleaned, None
