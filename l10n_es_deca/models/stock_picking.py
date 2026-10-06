# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError

DECA_PICKING_STATES = [
    ("not_required", "Not required"),
    ("not_generated", "Not generated"),
    ("draft", "Draft"),
    ("issued", "Issued"),
    ("closed", "Closed"),
    ("cancelled", "Cancelled"),
    ("attached", "Attached"),
    ("not_attached", "Not attached"),
]


class StockPicking(models.Model):
    _inherit = "stock.picking"

    deca_ids = fields.Many2many(
        "l10n.es.deca",
        "l10n_es_deca_picking_rel",
        "picking_id",
        "deca_id",
        string="DeCA documents",
        copy=False,
    )
    deca_id = fields.Many2one(
        "l10n.es.deca",
        string="Active DeCA",
        compute="_compute_deca_id",
        store=True,
    )
    deca_carrier_id = fields.Many2one(
        "res.partner",
        string="DeCA Carrier",
        domain=[("deca_carrier", "=", True)],
        compute="_compute_deca_carrier_id",
        store=True,
        readonly=False,
        help="Effective carrier performing the haulage. The company itself is "
        "proposed automatically when it has its own fleet.",
    )
    deca_state = fields.Selection(
        selection=DECA_PICKING_STATES,
        string="DeCA",
        compute="_compute_deca_state",
        store=True,
    )
    deca_received_file = fields.Binary(
        string="Attach DeCA",
        attachment=True,
        help="Copy of the DeCA handed over by the carrier when receiving the "
        "goods. On a receipt the DeCA is never generated: that obligation "
        "belongs to the sender.",
    )
    deca_received_filename = fields.Char(string="DeCA file name")

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("deca_ids", "deca_ids.state")
    def _compute_deca_id(self):
        for picking in self:
            active = picking.deca_ids.filtered(
                lambda d: d.state not in ("cancelled", "replaced")
            )
            picking.deca_id = active[:1]

    @api.depends("picking_type_code", "company_id.deca_carrier")
    def _compute_deca_carrier_id(self):
        for picking in self:
            if picking.deca_carrier_id:
                continue
            company = picking.company_id or self.env.company
            picking.deca_carrier_id = (
                company.partner_id if company.deca_carrier else False
            )

    @api.depends(
        "picking_type_code",
        "deca_id",
        "deca_id.state",
        "deca_received_file",
        "partner_id.country_id",
    )
    def _compute_deca_state(self):
        for picking in self:
            if picking.picking_type_code == "outgoing":
                if not picking.deca_id:
                    picking.deca_state = "not_generated"
                elif picking.deca_id.state == "modified":
                    picking.deca_state = "issued"
                else:
                    picking.deca_state = picking.deca_id.state
            elif picking.picking_type_code == "incoming":
                if not picking._is_domestic_origin():
                    picking.deca_state = "not_required"
                elif picking.deca_received_file:
                    picking.deca_state = "attached"
                else:
                    picking.deca_state = "not_attached"
            else:
                picking.deca_state = "not_required"

    def _is_domestic_origin(self):
        """The DeCA only covers domestic transport (origin and destination in Spain)."""
        self.ensure_one()
        country = self.partner_id.country_id or self.company_id.country_id
        return country.code == "ES"

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _check_deca_generation(self):
        non_outgoing = self.filtered(lambda p: p.picking_type_code != "outgoing")
        if non_outgoing:
            raise UserError(
                _(
                    "The DeCA is only generated for outgoing deliveries. On a "
                    "receipt the obligation belongs to whoever ships the goods: "
                    "attach the copy handed over by the carrier."
                )
            )
        already = self.filtered(lambda p: p.deca_id)
        if already:
            raise UserError(
                _(
                    "Deliveries %s are already covered by an active DeCA.",
                    ", ".join(already.mapped("name")),
                )
            )
        without_carrier = self.filtered(lambda p: not p.deca_carrier_id)
        if without_carrier:
            raise UserError(
                _(
                    "Select the DeCA Carrier on deliveries %s before generating "
                    "the document.",
                    ", ".join(without_carrier.mapped("name")),
                )
            )

    def _prepare_deca_vals(self):
        """Values of the DeCA covering these deliveries.

        Only what the delivery already knows is filled in here. Modules adding
        DeCA specific data to ``stock.picking`` extend this dictionary.
        """
        first = self[0]
        company = first.company_id
        dates = [p.scheduled_date.date() for p in self if p.scheduled_date]
        deadlines = [p.date_deadline.date() for p in self if p.date_deadline]
        transport_date = min(dates) if dates else fields.Date.context_today(self)
        service_end_date = max(deadlines) if deadlines else transport_date
        return {
            "company_id": company.id,
            "picking_ids": [fields.Command.set(self.ids)],
            "shipper_id": company.partner_id.id,
            "carrier_id": first.deca_carrier_id.id,
            "transport_date": transport_date,
            "service_end_date": max(service_end_date, transport_date),
        }

    def action_generate_deca(self):
        """Generate a draft DeCA for the selected deliveries."""
        pickings = self.filtered(lambda p: p.picking_type_code == "outgoing") or self
        pickings._check_deca_generation()
        carriers = pickings.mapped("deca_carrier_id")
        if len(carriers) > 1:
            raise UserError(
                _(
                    "Only deliveries sharing shipper and carrier can be grouped "
                    "in the same DeCA (section Sexto.1). You selected deliveries "
                    "with different carriers: %s.",
                    ", ".join(carriers.mapped("display_name")),
                )
            )
        deca = self.env["l10n.es.deca"].create(pickings._prepare_deca_vals())
        body = (
            _(
                "DeCA %s generated grouping this delivery with others "
                "(section Sexto.1).",
                deca.name,
            )
            if len(pickings) > 1
            else _("DeCA %s generated for this delivery.", deca.name)
        )
        for picking in pickings:
            picking.message_post(body=body)
        return {
            "type": "ir.actions.act_window",
            "res_model": "l10n.es.deca",
            "view_mode": "form",
            "res_id": deca.id,
        }

    def action_open_deca(self):
        self.ensure_one()
        if not self.deca_id:
            raise UserError(_("This delivery has no DeCA yet."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "l10n.es.deca",
            "view_mode": "form",
            "res_id": self.deca_id.id,
        }

    def write(self, vals):
        result = super().write(vals)
        if vals.get("deca_received_file"):
            for picking in self:
                picking.message_post(
                    body=_(
                        "DeCA received from the carrier, archived for this receipt."
                    ),
                    attachment_ids=picking._copy_deca_received_attachment().ids,
                )
        return result

    def _copy_deca_received_attachment(self):
        """Chatter-visible copy of the file stored in the binary field."""
        self.ensure_one()
        stored = (
            self.env["ir.attachment"]
            .sudo()
            .search(
                [
                    ("res_model", "=", self._name),
                    ("res_id", "=", self.id),
                    ("res_field", "=", "deca_received_file"),
                ],
                limit=1,
            )
        )
        if not stored:
            return self.env["ir.attachment"]
        return stored.copy(
            {
                "name": self.deca_received_filename or stored.name,
                "res_field": False,
            }
        )
