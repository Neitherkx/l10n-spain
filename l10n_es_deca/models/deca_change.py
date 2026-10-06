# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.exceptions import UserError


class L10nEsDecaChange(models.Model):
    _name = "l10n.es.deca.change"
    _description = "DeCA En-Route Modification (Method A)"
    _order = "change_date desc, id desc"

    deca_id = fields.Many2one(
        "l10n.es.deca",
        string="DeCA",
        required=True,
        ondelete="cascade",
        index=True,
    )
    field_label = fields.Char(string="Data", required=True, readonly=True)
    field_name = fields.Char(string="Technical field", readonly=True)
    old_value = fields.Char(string="Previous value", readonly=True)
    new_value = fields.Char(string="New value", readonly=True)
    reason = fields.Char(required=True, readonly=True)
    change_date = fields.Datetime(
        string="Date",
        required=True,
        readonly=True,
        default=fields.Datetime.now,
    )
    user_id = fields.Many2one(
        "res.users",
        string="User",
        required=True,
        readonly=True,
        default=lambda self: self.env.user,
    )

    # Section Quinto.1 forbids rewriting the history, so there is no super() call.
    def write(self, vals):  # pylint: disable=method-required-super
        raise UserError(
            _(
                "The DeCA modification history is immutable (Resolution of "
                "5 June 2026, section Quinto.1)."
            )
        )

    # pylint: disable=method-required-super,no-raise-unlink
    def unlink(self):
        raise UserError(
            _(
                "The DeCA modification history is immutable (Resolution of "
                "5 June 2026, section Quinto.1)."
            )
        )
