# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    deca_carrier = fields.Boolean(
        related="company_id.deca_carrier",
        string="Own fleet (DeCA Carrier)",
        readonly=False,
    )
    deca_public_domain = fields.Char(
        related="company_id.deca_public_domain",
        string="DeCA public domain",
        readonly=False,
    )
    deca_qr_page = fields.Integer(
        related="company_id.deca_qr_page",
        string="QR page",
        readonly=False,
    )
    deca_qr_position_x = fields.Float(
        related="company_id.deca_qr_position_x",
        string="QR horizontal position",
        readonly=False,
    )
    deca_qr_position_y = fields.Float(
        related="company_id.deca_qr_position_y",
        string="QR vertical position",
        readonly=False,
    )
    deca_qr_size = fields.Float(
        related="company_id.deca_qr_size",
        string="QR size",
        readonly=False,
    )
