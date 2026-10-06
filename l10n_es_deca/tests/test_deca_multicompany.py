# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import DecaCommon

SECOND_COMPANY_VAT = "ES B65432106"


@tagged("post_install", "-at_install")
class TestDecaMultiCompany(DecaCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_b = cls.env["res.company"].create(
            {
                "name": "Isonor Levante SL",
                "country_id": cls.spain.id,
                "deca_public_domain": "deca.levante.example",
            }
        )
        cls.company_b.partner_id.write(
            {
                "vat": SECOND_COMPANY_VAT,
                "street": "Calle Alicante 5",
                "zip": "46001",
                "city": "Valencia",
                "country_id": cls.spain.id,
            }
        )
        cls.env.user.company_ids = [fields.Command.link(cls.company_b.id)]
        cls.user_b = cls.env["res.users"].create(
            {
                "name": "Levante User",
                "login": "deca_user_b",
                "company_id": cls.company_b.id,
                "company_ids": [fields.Command.set(cls.company_b.ids)],
                "groups_id": [
                    fields.Command.link(cls.env.ref("l10n_es_deca.group_deca_user").id),
                    fields.Command.link(cls.env.ref("stock.group_stock_user").id),
                ],
            }
        )

    def _picking_type_out_b(self):
        return self.env["stock.picking.type"].search(
            [
                ("code", "=", "outgoing"),
                ("company_id", "=", self.company_b.id),
            ],
            limit=1,
        )

    def _create_deca_b(self):
        picking_type = self._picking_type_out_b()
        picking = (
            self.env["stock.picking"]
            .with_company(self.company_b)
            .create(
                {
                    "partner_id": self.customer.id,
                    "picking_type_id": picking_type.id,
                    "location_id": picking_type.default_location_src_id.id,
                    "location_dest_id": picking_type.default_location_dest_id.id,
                    "company_id": self.company_b.id,
                    "deca_carrier_id": self.carrier.id,
                }
            )
        )
        self.env["stock.move"].with_company(self.company_b).create(
            {
                "picking_id": picking.id,
                "name": self.product.name,
                "product_id": self.product.id,
                "product_uom_qty": 5.0,
                "product_uom": self.product.uom_id.id,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
            }
        )
        return (
            self.env["l10n.es.deca"]
            .with_company(self.company_b)
            .create(
                {
                    "company_id": self.company_b.id,
                    "picking_ids": [fields.Command.set(picking.ids)],
                    "shipper_id": self.company_b.partner_id.id,
                    "carrier_id": self.carrier.id,
                    "transport_date": self.today,
                    "service_end_date": self.today,
                }
            )
        )

    def test_record_rule_isolates_decas(self):
        deca_a = self._create_deca()
        deca_b = self._create_deca_b()
        visible = self.env["l10n.es.deca"].with_user(self.user_b).search([])
        self.assertIn(deca_b, visible)
        self.assertNotIn(deca_a, visible)

    def test_record_rule_isolates_lines_and_logs(self):
        deca_a = self._create_deca()
        deca_a.action_issue()
        deca_a._log_public_access("10.0.0.1", "GET", 200, "pytest")
        as_b = self.env(user=self.user_b)
        self.assertFalse(
            as_b["l10n.es.deca.line"].search([("deca_id", "=", deca_a.id)])
        )
        self.assertFalse(
            as_b["l10n.es.deca.access.log"].search([("deca_id", "=", deca_a.id)])
        )

    def test_sequence_is_company_aware(self):
        seq_a = self.env["l10n.es.deca"]._get_sequence(self.company)
        seq_b = self.env["l10n.es.deca"]._get_sequence(self.company_b)
        self.assertNotEqual(seq_a, seq_b)
        self.assertEqual(seq_b.company_id, self.company_b)
        self.assertTrue(seq_a.next_by_id().startswith("DECA/"))
        self.assertTrue(seq_b.next_by_id().startswith("DECA/"))
        seq_b.prefix = "DECA-LEV/%(year)s/"
        self.assertTrue(seq_b.next_by_id().startswith("DECA-LEV/"))

    def test_picking_company_must_match_deca_company(self):
        picking_b_deca = self._create_deca_b()
        picking_a = self._create_picking()
        with self.assertRaises(ValidationError):
            picking_b_deca.write({"picking_ids": [fields.Command.link(picking_a.id)]})

    def test_vehicle_of_other_company_is_rejected(self):
        vehicle_b = self.env["l10n.es.deca.vehicle"].create(
            {
                "name": "7777 LEV",
                "vehicle_type": "tractor",
                "partner_id": self.carrier.id,
                "company_id": self.company_b.id,
            }
        )
        deca_a = self._create_deca()
        with self.assertRaises(ValidationError):
            deca_a.tractor_plate_id = vehicle_b

    def test_shared_vehicle_is_allowed_in_any_company(self):
        self.tractor.company_id = False
        deca_b = self._create_deca_b()
        deca_b.tractor_plate_id = self.tractor
        self.assertEqual(deca_b.tractor_plate_id, self.tractor)

    def test_vehicle_record_rule(self):
        vehicle_a = self.env["l10n.es.deca.vehicle"].create(
            {
                "name": "1111 AAA",
                "vehicle_type": "tractor",
                "partner_id": self.carrier.id,
                "company_id": self.company.id,
            }
        )
        visible = self.env["l10n.es.deca.vehicle"].with_user(self.user_b).search([])
        self.assertNotIn(vehicle_a, visible)

    def test_public_url_uses_company_domain(self):
        deca_b = self._create_deca_b()
        self.assertEqual(deca_b._get_public_base_url(), "https://deca.levante.example")
        deca_a = self._create_deca()
        self.assertEqual(deca_a._get_public_base_url(), "https://deca.test.example")

    def test_public_url_falls_back_to_base_url_not_website(self):
        """The commercial website does not serve /deca/<token>, so it is no base."""
        self.company.deca_public_domain = False
        self.company.website = "https://www.marketing.example"
        deca = self._create_deca()
        base_url = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        )
        self.assertEqual(deca._get_public_base_url(), base_url.rstrip("/"))
        self.assertNotIn("marketing.example", deca._get_public_base_url())

    def test_same_number_allowed_in_different_companies(self):
        deca_a = self._create_deca()
        deca_b = self._create_deca_b()
        number = "DECA/2026/09999"
        deca_a.write({"name": number, "state": "issued"})
        deca_b.write({"name": number, "state": "issued"})
        self.assertEqual(deca_a.name, deca_b.name)
