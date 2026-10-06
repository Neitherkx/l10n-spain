# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.deca_document import METHOD_A_FIELDS


class L10nEsDecaModifyWizard(models.TransientModel):
    _name = "l10n.es.deca.modify.wizard"
    _description = "Register DeCA Modification (Method A)"

    deca_id = fields.Many2one("l10n.es.deca", required=True, ondelete="cascade")
    carrier_id = fields.Many2one(related="deca_id.carrier_id")
    field_name = fields.Selection(
        selection=METHOD_A_FIELDS,
        string="Field to modify",
        required=True,
        default="tractor_plate_id",
    )
    new_tractor_plate_id = fields.Many2one(
        "l10n.es.deca.vehicle",
        string="New tractor plate",
    )
    new_trailer_plate_id = fields.Many2one(
        "l10n.es.deca.vehicle",
        string="New trailer plate",
    )
    new_transport_date = fields.Date(string="New transport date")
    new_service_end_date = fields.Date(string="New service end date")
    new_note = fields.Text(string="New notes")
    reason = fields.Char(required=True)

    _NEW_VALUE_FIELDS = {
        "tractor_plate_id": "new_tractor_plate_id",
        "trailer_plate_id": "new_trailer_plate_id",
        "transport_date": "new_transport_date",
        "service_end_date": "new_service_end_date",
        "note": "new_note",
    }

    @api.onchange("field_name")
    def _onchange_field_name(self):
        deca = self.deca_id
        self.new_tractor_plate_id = deca.tractor_plate_id
        self.new_trailer_plate_id = deca.trailer_plate_id
        self.new_transport_date = deca.transport_date
        self.new_service_end_date = deca.service_end_date
        self.new_note = deca.note

    def _format_value(self, value):
        if not value:
            return ""
        if hasattr(value, "display_name"):
            return value.display_name
        return str(value)

    def action_apply(self):
        self.ensure_one()
        deca = self.deca_id
        if deca.state not in ("issued", "modified"):
            raise UserError(
                _("Only an issued or already modified DeCA can be modified.")
            )
        field_name = self.field_name
        new_value = self[self._NEW_VALUE_FIELDS[field_name]]
        old_value = deca[field_name]
        if new_value == old_value:
            raise UserError(_("The new value matches the current one."))

        labels = dict(self._fields["field_name"]._description_selection(self.env))
        self.env["l10n.es.deca.change"].create(
            {
                "deca_id": deca.id,
                "field_name": field_name,
                "field_label": labels[field_name],
                "old_value": self._format_value(old_value),
                "new_value": self._format_value(new_value),
                "reason": self.reason,
            }
        )
        deca.write(
            {
                field_name: new_value.id if hasattr(new_value, "id") else new_value,
                "state": "modified",
            }
        )
        # Method A: same token, same URL and same QR; only the PDF is rebuilt.
        deca._store_pdf()
        deca.message_post(
            body=_(
                "Modification registered (Method A) on %(label)s: "
                "%(old)s -> %(new)s. Reason: %(reason)s. New SHA-256: %(hash)s",
                label=labels[field_name],
                old=self._format_value(old_value) or _("(empty)"),
                new=self._format_value(new_value),
                reason=self.reason,
                hash=deca.pdf_sha256,
            )
        )
        return {"type": "ir.actions.act_window_close"}
