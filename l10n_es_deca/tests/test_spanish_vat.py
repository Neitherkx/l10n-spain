# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase

from ..models.spanish_vat import check_spanish_vat, normalize_vat


class TestSpanishVat(TransactionCase):
    def test_normalize(self):
        self.assertEqual(normalize_vat("es b-12.345.674 "), "B12345674")

    def test_valid_nif(self):
        self.assertTrue(check_spanish_vat("12345678Z"))

    def test_invalid_nif(self):
        self.assertFalse(check_spanish_vat("12345678A"))

    def test_valid_nie(self):
        # X0000000T: 00000000 % 23 = 0 -> letra T
        self.assertTrue(check_spanish_vat("X0000000T"))

    def test_invalid_nie(self):
        self.assertFalse(check_spanish_vat("X0000000A"))

    def test_valid_cif_number_control(self):
        self.assertTrue(check_spanish_vat("A58818501"))
        self.assertTrue(check_spanish_vat("ESB12345674"))

    def test_invalid_cif(self):
        self.assertFalse(check_spanish_vat("A58818509"))

    def test_garbage(self):
        for value in ("", None, "ABC", "1234", "ZZ1234567"):
            self.assertFalse(check_spanish_vat(value))
