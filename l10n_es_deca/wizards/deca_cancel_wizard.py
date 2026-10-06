# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError


class L10nEsDecaCancelWizard(models.TransientModel):
    _name = "l10n.es.deca.cancel.wizard"
    _description = "Cancel DeCA"

    deca_id = fields.Many2one("l10n.es.deca", required=True, ondelete="cascade")
    reason = fields.Char(required=True)

    def action_cancel(self):
        self.ensure_one()
        deca = self.deca_id
        if not self.env.user.has_group("l10n_es_deca.group_deca_manager"):
            raise AccessError(_("Only a DeCA Administrator can cancel a document."))
        if deca.state not in ("issued", "modified"):
            raise UserError(_("Only an issued DeCA can be cancelled."))
        if deca.transport_date <= fields.Date.context_today(self):
            raise UserError(
                _(
                    "Cancellation is only possible if the service never starts. "
                    "The transport date of %s has already been reached: use "
                    "'Register modification' (Method A) or 'Reissue DeCA' "
                    "(Method B).",
                    deca.name,
                )
            )
        deca.write(
            {
                "state": "cancelled",
                "cancel_reason": self.reason,
                "cancel_date": fields.Datetime.now(),
            }
        )
        deca.message_post(
            body=_(
                "DeCA cancelled. Reason: %s. The PDF and the token are kept due "
                "to the retention obligation, but the public link stops serving "
                "the file.",
                self.reason,
            )
        )
        return {"type": "ir.actions.act_window_close"}
