# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields
from odoo.tests.common import TransactionCase

# Tax IDs with a valid check digit, required to be able to issue.
SHIPPER_VAT = "ES B12345674"
CARRIER_VAT = "ES A58818501"


class DecaCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.company = cls.env.company
        cls.spain = cls.env.ref("base.es")
        cls.company.write(
            {
                "deca_public_domain": "deca.test.example",
                "country_id": cls.spain.id,
            }
        )
        cls.company.partner_id.write(
            {
                "vat": SHIPPER_VAT,
                "street": "Calle Mayor 1",
                "zip": "28001",
                "city": "Madrid",
                "country_id": cls.spain.id,
            }
        )

        cls.carrier = cls.env["res.partner"].create(
            {
                "name": "Transportes DeCA SA",
                "company_type": "company",
                "vat": CARRIER_VAT,
                "street": "Poligono Sur 4",
                "zip": "50014",
                "city": "Zaragoza",
                "country_id": cls.spain.id,
                "deca_carrier": True,
                "deca_authorization": "MDP-1234567",
                "email": "trafico@transportes-deca.example",
            }
        )
        cls.other_carrier = cls.env["res.partner"].create(
            {
                "name": "Other Carrier SL",
                "company_type": "company",
                "vat": "ES 12345678Z",
                "country_id": cls.spain.id,
                "deca_carrier": True,
            }
        )
        cls.customer = cls.env["res.partner"].create(
            {
                "name": "Cliente Destino SL",
                "company_type": "company",
                "street": "Avenida del Puerto 22",
                "zip": "46023",
                "city": "Valencia",
                "country_id": cls.spain.id,
            }
        )

        cls.tractor = cls.env["l10n.es.deca.vehicle"].create(
            {
                "name": "1234 ABC",
                "vehicle_type": "tractor",
                "partner_id": cls.carrier.id,
            }
        )
        cls.tractor_spare = cls.env["l10n.es.deca.vehicle"].create(
            {
                "name": "5678 DEF",
                "vehicle_type": "tractor",
                "partner_id": cls.carrier.id,
            }
        )
        cls.trailer = cls.env["l10n.es.deca.vehicle"].create(
            {
                "name": "R 9012 BBB",
                "vehicle_type": "trailer",
                "partner_id": cls.carrier.id,
            }
        )
        cls.foreign_tractor = cls.env["l10n.es.deca.vehicle"].create(
            {
                "name": "0000 ZZZ",
                "vehicle_type": "tractor",
                "partner_id": cls.other_carrier.id,
            }
        )

        cls.product = cls.env["product.product"].create(
            {
                "name": "Cement pallet",
                "is_storable": True,
                "weight": 25.0,
            }
        )
        cls.picking_type_out = cls.env.ref("stock.picking_type_out")
        cls.picking_type_in = cls.env.ref("stock.picking_type_in")
        cls.today = fields.Date.context_today(cls.env["l10n.es.deca"])

    @classmethod
    def _create_picking(cls, partner=None, picking_type=None, qty=10.0):
        picking_type = picking_type or cls.picking_type_out
        picking = cls.env["stock.picking"].create(
            {
                "partner_id": (partner or cls.customer).id,
                "picking_type_id": picking_type.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": picking_type.default_location_dest_id.id,
                "deca_carrier_id": cls.carrier.id,
            }
        )
        cls.env["stock.move"].create(
            {
                "picking_id": picking.id,
                "name": cls.product.name,
                "product_id": cls.product.id,
                "product_uom_qty": qty,
                "product_uom": cls.product.uom_id.id,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
            }
        )
        return picking

    def _create_deca(self, pickings=None, **kwargs):
        pickings = pickings or self._create_picking()
        vals = {
            "picking_ids": [fields.Command.set(pickings.ids)],
            "shipper_id": self.company.partner_id.id,
            "carrier_id": self.carrier.id,
            "tractor_plate_id": self.tractor.id,
            "trailer_plate_id": self.trailer.id,
            "transport_date": self.today,
            "service_end_date": self.today,
        }
        vals.update(kwargs)
        return self.env["l10n.es.deca"].create(vals)
