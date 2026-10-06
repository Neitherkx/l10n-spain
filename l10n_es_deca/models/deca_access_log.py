# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# One-year retention required for the access records.
ACCESS_LOG_RETENTION_DAYS = 365


class L10nEsDecaAccessLog(models.Model):
    _name = "l10n.es.deca.access.log"
    _description = "DeCA Public Access Log"
    _order = "access_date desc, id desc"

    deca_id = fields.Many2one(
        "l10n.es.deca",
        string="DeCA",
        required=True,
        ondelete="cascade",
        index=True,
    )
    access_date = fields.Datetime(
        string="Date",
        required=True,
        readonly=True,
        default=fields.Datetime.now,
        index=True,
    )
    ip_address = fields.Char(string="IP address", readonly=True)
    method = fields.Char(readonly=True)
    status_code = fields.Integer(string="Status code", readonly=True)
    user_agent = fields.Char(string="User agent", readonly=True)

    @api.model
    def _cron_purge_access_logs(self):
        """Purge the access records older than the retention period."""
        limit_date = fields.Datetime.subtract(
            fields.Datetime.now(), days=ACCESS_LOG_RETENTION_DAYS
        )
        logs = self.sudo().search([("access_date", "<", limit_date)])
        if logs:
            _logger.info("DeCA: purging %s access records", len(logs))
            logs.unlink()
        return True
