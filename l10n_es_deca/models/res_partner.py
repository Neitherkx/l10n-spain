# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .spanish_vat import check_spanish_vat


class ResPartner(models.Model):
    _inherit = "res.partner"

    deca_carrier = fields.Boolean(
        string="DeCA Carrier",
        help="Flag this contact as an effective carrier for DeCA purposes. You "
        "will be able to select it on deliveries and manage its plate "
        "catalogue in the Vehicles tab.",
    )
    deca_authorization = fields.Char(
        string="Transport authorization",
        help="Number of the carrier's transport card (MDP/MDL).",
    )
    deca_vehicle_ids = fields.One2many(
        "l10n.es.deca.vehicle",
        "partner_id",
        string="Vehicles",
    )
    deca_vehicle_count = fields.Integer(compute="_compute_deca_vehicle_count")

    @api.depends("deca_vehicle_ids")
    def _compute_deca_vehicle_count(self):
        for partner in self:
            partner.deca_vehicle_count = len(partner.deca_vehicle_ids)

    @api.constrains("deca_carrier", "vat")
    def _check_deca_carrier_vat(self):
        for partner in self:
            if not partner.deca_carrier:
                continue
            if not partner.vat:
                raise ValidationError(
                    _(
                        "A DeCA carrier needs a tax ID: it is mandatory data of "
                        "the document (%s).",
                        partner.display_name,
                    )
                )
            if not check_spanish_vat(partner.vat):
                raise ValidationError(
                    _(
                        "Tax ID %(vat)s of %(partner)s is not valid.",
                        vat=partner.vat,
                        partner=partner.display_name,
                    )
                )
