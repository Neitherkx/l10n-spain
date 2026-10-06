# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import DecaCommon


@tagged("post_install", "-at_install")
class TestStockPicking(DecaCommon):
    def test_outgoing_without_deca(self):
        picking = self._create_picking()
        self.assertEqual(picking.deca_state, "not_generated")
        self.assertFalse(picking.deca_id)

    def test_generate_deca_from_picking(self):
        picking = self._create_picking()
        action = picking.action_generate_deca()
        deca = self.env["l10n.es.deca"].browse(action["res_id"])
        self.assertEqual(picking.deca_id, deca)
        self.assertEqual(picking.deca_state, "draft")
        self.assertEqual(deca.shipper_id, self.company.partner_id)
        self.assertEqual(deca.carrier_id, self.carrier)
        self.assertEqual(deca.picking_ids, picking)
        deca.tractor_plate_id = self.tractor
        deca.action_issue()
        self.assertEqual(picking.deca_state, "issued")

    def test_generate_grouped_deca(self):
        pickings = self._create_picking() | self._create_picking()
        action = pickings.action_generate_deca()
        deca = self.env["l10n.es.deca"].browse(action["res_id"])
        self.assertTrue(deca.is_grouped)
        self.assertEqual(deca.picking_ids, pickings)

    def test_generate_twice_is_blocked(self):
        picking = self._create_picking()
        picking.action_generate_deca()
        with self.assertRaises(UserError):
            picking.action_generate_deca()

    def test_generate_requires_carrier(self):
        picking = self._create_picking()
        picking.deca_carrier_id = False
        with self.assertRaises(UserError):
            picking.action_generate_deca()

    def test_generate_on_reception_is_blocked(self):
        reception = self._create_picking(picking_type=self.picking_type_in)
        with self.assertRaises(UserError):
            reception.action_generate_deca()

    def test_modified_deca_shows_as_issued_on_picking(self):
        picking = self._create_picking()
        deca = self._create_deca(picking)
        deca.action_issue()
        self.env["l10n.es.deca.modify.wizard"].create(
            {
                "deca_id": deca.id,
                "field_name": "note",
                "new_note": "Cambio de ruta",
                "reason": "Obras en la N-II",
            }
        ).action_apply()
        self.assertEqual(deca.state, "modified")
        self.assertEqual(picking.deca_state, "issued")

    def test_domestic_reception_requires_attachment(self):
        reception = self._create_picking(picking_type=self.picking_type_in)
        self.assertEqual(reception.deca_state, "not_attached")
        reception.deca_received_filename = "deca_proveedor.pdf"
        reception.deca_received_file = base64.b64encode(b"%PDF-1.4 fake")
        self.assertEqual(reception.deca_state, "attached")
        attachments = reception.message_ids.mapped("attachment_ids")
        self.assertTrue(attachments)
        self.assertEqual(attachments[0].name, "deca_proveedor.pdf")

    def test_foreign_reception_does_not_require_deca(self):
        france = self.env.ref("base.fr")
        supplier = self.env["res.partner"].create(
            {"name": "Fournisseur SARL", "country_id": france.id}
        )
        reception = self._create_picking(
            partner=supplier, picking_type=self.picking_type_in
        )
        self.assertEqual(reception.deca_state, "not_required")

    def test_own_fleet_sets_default_carrier(self):
        self.company.deca_carrier = True
        picking = self.env["stock.picking"].create(
            {
                "partner_id": self.customer.id,
                "picking_type_id": self.picking_type_out.id,
                "location_id": self.picking_type_out.default_location_src_id.id,
                "location_dest_id": (self.picking_type_out.default_location_dest_id.id),
            }
        )
        self.assertEqual(picking.deca_carrier_id, self.company.partner_id)
        self.assertTrue(self.company.partner_id.deca_carrier)

    def test_dates_default_from_the_schedule(self):
        picking = self._create_picking()
        vals = picking._prepare_deca_vals()
        self.assertEqual(vals["transport_date"], picking.scheduled_date.date())
        self.assertGreaterEqual(vals["service_end_date"], vals["transport_date"])
