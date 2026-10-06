# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.exceptions import UserError


class DecaOwnDocument(models.TransientModel):
    _name = "l10n.es.deca.own.document"
    _description = "Convert your own document into a DeCA"

    deca_id = fields.Many2one(
        "l10n.es.deca",
        string="DeCA",
        required=True,
        ondelete="cascade",
    )
    document = fields.Binary(
        required=True,
        help="Your own document in PDF. The DeCA QR code is stamped on it and "
        "that stamped file becomes the document to be carried and the one the "
        "authority downloads, instead of the one Odoo generates.",
    )
    document_filename = fields.Char(string="File name")

    def action_confirm(self):
        """Store the document and jump straight to the QR placement screen."""
        self.ensure_one()
        if self.deca_id.state != "draft":
            raise UserError(
                _("Your own document can only be attached while the DeCA is a draft.")
            )
        self.deca_id.write(
            {
                "custom_pdf": self.document,
                "custom_pdf_filename": self.document_filename,
            }
        )
        return self.deca_id.action_configure_qr()
