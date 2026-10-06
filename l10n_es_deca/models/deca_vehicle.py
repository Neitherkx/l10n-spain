# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

VEHICLE_TYPES = [
    ("tractor", "Tractor unit"),
    ("trailer", "Trailer / Semi-trailer"),
]


class L10nEsDecaVehicle(models.Model):
    _name = "l10n.es.deca.vehicle"
    _description = "DeCA Vehicle (tractor or trailer plate)"
    _order = "partner_id, vehicle_type, name"
    _rec_name = "name"

    name = fields.Char(
        string="Plate",
        required=True,
        help="Plate number as it must appear on the DeCA.",
    )
    vehicle_type = fields.Selection(
        selection=VEHICLE_TYPES,
        string="Type",
        required=True,
        default="tractor",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Carrier",
        required=True,
        ondelete="cascade",
        index=True,
        domain=[("deca_carrier", "=", True)],
    )
    active = fields.Boolean(default=True)
    note = fields.Char(string="Notes")
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        index=True,
        default=lambda self: self.env.company,
        help="Leave it empty to share the plate across all companies.",
    )

    _sql_constraints = [
        (
            "plate_unique_per_carrier",
            "UNIQUE(partner_id, name)",
            "The plate is already registered for this carrier.",
        ),
    ]

    @api.constrains("partner_id")
    def _check_partner_is_carrier(self):
        for vehicle in self:
            if not vehicle.partner_id.deca_carrier:
                raise ValidationError(
                    _(
                        "Contact %s is not flagged as a DeCA Carrier, so it "
                        "cannot have plates assigned.",
                        vehicle.partner_id.display_name,
                    )
                )

    @api.depends("name", "vehicle_type")
    def _compute_display_name(self):
        labels = dict(
            self.env["l10n.es.deca.vehicle"]
            ._fields["vehicle_type"]
            ._description_selection(self.env)
        )
        for vehicle in self:
            vehicle.display_name = (
                f"{vehicle.name} ({labels.get(vehicle.vehicle_type, '')})"
            )
