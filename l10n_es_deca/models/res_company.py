# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    deca_carrier = fields.Boolean(
        string="DeCA Carrier",
        compute="_compute_deca_carrier",
        inverse="_inverse_deca_carrier",
        help="Enable it if your own company performs the transport (own "
        "fleet). The DeCA will then default the carrier to the company data.",
    )
    deca_public_domain = fields.Char(
        string="DeCA public domain",
        help="Leave it empty unless a reverse proxy publishes this company's "
        "DeCA under a different domain name (for example deca.mycompany.es). "
        "By default the instance's own domain (web.base.url) is used, which is "
        "what answers /deca/<token>.",
    )

    deca_qr_page = fields.Integer(
        string="QR page",
        default=1,
        help="Page of the uploaded PDF the QR code is stamped on by default.",
    )
    deca_qr_position_x = fields.Float(
        string="QR horizontal position",
        default=72.0,
        help="Distance from the left edge, as a percentage of the page width.",
    )
    deca_qr_position_y = fields.Float(
        string="QR vertical position",
        default=4.0,
        help="Distance from the top edge, as a percentage of the page height.",
    )
    deca_qr_size = fields.Float(
        string="QR size",
        default=18.0,
        help="Side of the QR square, as a percentage of the page width.",
    )

    @api.depends("partner_id.deca_carrier")
    def _compute_deca_carrier(self):
        for company in self:
            company.deca_carrier = company.partner_id.deca_carrier

    def _inverse_deca_carrier(self):
        for company in self:
            company.partner_id.deca_carrier = company.deca_carrier

    @api.constrains("deca_public_domain")
    def _check_deca_public_domain(self):
        for company in self:
            domain = (company.deca_public_domain or "").strip()
            if domain and ("/" in domain.split("://")[-1] or " " in domain):
                raise ValidationError(
                    _(
                        "The DeCA public domain must be a domain name only (for "
                        "example deca.mycompany.es), without path or spaces."
                    )
                )
