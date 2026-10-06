# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.depends("create_date")
    def _compute_tour_enabled(self):
        """Offer the onboarding to whoever is going to issue DeCA documents.

        Odoo only turns onboarding on for an administrator of a database
        without demo data, so a plain DeCA user would never be shown the guide.
        The flag stays editable, so anyone switching it off in their
        preferences keeps it off.
        """
        res = super()._compute_tour_enabled()
        for user in self:
            if not user.tour_enabled and user.has_group("l10n_es_deca.group_deca_user"):
                user.tour_enabled = True
        return res
