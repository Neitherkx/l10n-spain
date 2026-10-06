# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class L10nEsDecaLine(models.Model):
    _name = "l10n.es.deca.line"
    _description = "DeCA Shipment Line"
    _order = "deca_id, picking_id, id"

    deca_id = fields.Many2one(
        "l10n.es.deca",
        string="DeCA",
        required=True,
        ondelete="cascade",
        index=True,
    )
    picking_id = fields.Many2one(
        "stock.picking",
        string="Delivery",
        required=True,
        ondelete="cascade",
        index=True,
    )
    origin_address = fields.Char(string="Origin")
    destination_address = fields.Char(string="Destination")
    transport_date = fields.Date(string="Transport date")
    product_id = fields.Many2one("product.product", string="Product")
    # Section Segundo (d): nature of the goods.
    nature = fields.Char(string="Nature of the goods")
    quantity = fields.Float(digits="Product Unit of Measure")
    product_uom_id = fields.Many2one("uom.uom", string="Unit of measure")
    weight = fields.Float(string="Weight (kg)", digits="Stock Weight")

    @api.depends("product_id", "nature")
    def _compute_display_name(self):
        for line in self:
            line.display_name = line.nature or line.product_id.display_name or ""
