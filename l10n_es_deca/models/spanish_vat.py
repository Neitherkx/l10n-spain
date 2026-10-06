# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Check digit validation for Spanish NIF / NIE / CIF numbers."""

import re

_NIF_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
_CIF_CONTROL_LETTERS = "JABCDEFGHI"
_NIE_PREFIX = {"X": "0", "Y": "1", "Z": "2"}
# Organizations whose check digit is always a letter.
_CIF_LETTER_ONLY = "PQRSNW"
# Organizations whose check digit is always a number.
_CIF_NUMBER_ONLY = "ABEH"


def normalize_vat(vat):
    """Return the VAT without spaces, dashes or the ES country prefix."""
    if not vat:
        return ""
    value = re.sub(r"[^A-Z0-9]", "", vat.upper())
    if value.startswith("ES"):
        value = value[2:]
    return value


def _check_nif(value):
    return value[8] == _NIF_LETTERS[int(value[:8]) % 23]


def _check_nie(value):
    body = _NIE_PREFIX[value[0]] + value[1:8]
    return value[8] == _NIF_LETTERS[int(body) % 23]


def _check_cif(value):
    letter, body, control = value[0], value[1:8], value[8]
    total = 0
    for index, char in enumerate(body):
        digit = int(char)
        if index % 2 == 0:  # odd positions of the CIF (1-indexed)
            doubled = digit * 2
            total += doubled // 10 + doubled % 10
        else:
            total += digit
    remainder = (10 - total % 10) % 10
    if letter in _CIF_NUMBER_ONLY:
        return control == str(remainder)
    if letter in _CIF_LETTER_ONLY:
        return control == _CIF_CONTROL_LETTERS[remainder]
    return control in (str(remainder), _CIF_CONTROL_LETTERS[remainder])


def check_spanish_vat(vat):
    """Validate the check digit of a Spanish NIF, NIE or CIF.

    Return ``False`` for any value not following one of those three formats.
    """
    value = normalize_vat(vat)
    if not value or len(value) != 9:
        return False
    if re.fullmatch(r"\d{8}[A-Z]", value):
        return _check_nif(value)
    if re.fullmatch(r"[XYZ]\d{7}[A-Z]", value):
        return _check_nie(value)
    if re.fullmatch(r"[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]", value):
        return _check_cif(value)
    return False
