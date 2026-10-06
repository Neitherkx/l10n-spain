# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.exceptions import UserError


class L10nEsDecaReissueWizard(models.TransientModel):
    _name = "l10n.es.deca.reissue.wizard"
    _description = "Reissue DeCA (Method B)"

    deca_id = fields.Many2one("l10n.es.deca", required=True, ondelete="cascade")
    reason = fields.Char(
        required=True,
        help="Why this DeCA needs to be reissued instead of modified.",
    )

    def action_reissue(self):
        self.ensure_one()
        origin = self.deca_id
        if origin.state not in ("issued", "modified"):
            raise UserError(_("Only an issued DeCA can be reissued."))
        if origin.replacement_deca_id:
            raise UserError(
                _(
                    "This DeCA already has a replacement: %s.",
                    origin.replacement_deca_id.name,
                )
            )
        new_deca = origin.copy(
            {
                "state": "draft",
                "replaced_deca_id": origin.id,
                "reissue_reason": self.reason,
                "picking_ids": [fields.Command.set(origin.picking_ids.ids)],
            }
        )
        new_deca._sync_lines()
        new_deca.message_post(
            body=_(
                "Reissued from %(origin)s (Method B). Reason: %(reason)s",
                origin=origin.name,
                reason=self.reason,
            )
        )
        origin.message_post(
            body=_(
                "Reissuance in progress (Method B): a new draft has been "
                "created. Reason: %(reason)s",
                reason=self.reason,
            )
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "l10n.es.deca",
            "view_mode": "form",
            "res_id": new_deca.id,
        }
