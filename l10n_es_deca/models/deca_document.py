# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import hashlib
import io
import logging
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.pdf import PdfFileReader, PdfFileWriter

from .spanish_vat import check_spanish_vat

_logger = logging.getLogger(__name__)

try:
    import qrcode
except ImportError:  # pragma: no cover
    qrcode = None
    _logger.debug("The python library 'qrcode' is not installed.")

try:
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
except ImportError:  # pragma: no cover
    canvas = ImageReader = None
    _logger.debug("The python library 'reportlab' is not installed.")

# Resolution, section Segundo.1: the file cannot exceed 5 MB.
MAX_PDF_BYTES = 5 * 1024 * 1024
# Section Tercero.5: the public download is disabled 7 calendar days after the
# end of the service.
PUBLIC_ACCESS_DAYS = 7
# Section Tercero.2: opaque, unique token with no expiry of its own.
TOKEN_BYTES = 16

DECA_STATES = [
    ("draft", "Draft"),
    ("issued", "Issued"),
    ("modified", "Modified"),
    ("closed", "Closed"),
    ("replaced", "Replaced"),
    ("cancelled", "Cancelled"),
]

# Fields that Method A allows to correct on an already issued document.
METHOD_A_FIELDS = [
    ("tractor_plate_id", "Tractor plate"),
    ("trailer_plate_id", "Trailer plate"),
    ("transport_date", "Transport date"),
    ("service_end_date", "Service end date"),
    ("note", "Notes"),
]


class L10nEsDeca(models.Model):
    _name = "l10n.es.deca"
    _description = "Electronic Administrative Control Document (DeCA)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "issue_date desc, id desc"

    name = fields.Char(
        string="Number",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("Draft"),
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        readonly=True,
        default=lambda self: self.env.company,
    )
    state = fields.Selection(
        selection=DECA_STATES,
        string="Status",
        default="draft",
        required=True,
        copy=False,
        tracking=True,
    )

    picking_ids = fields.Many2many(
        "stock.picking",
        "l10n_es_deca_picking_rel",
        "deca_id",
        "picking_id",
        string="Deliveries",
        copy=False,
        tracking=True,
        help="Outgoing deliveries covered by this DeCA. Several deliveries can "
        "only be grouped (section Sexto.1) if they share shipper and carrier. "
        "They may be left empty when the document to be carried is your own "
        "file instead of the one Odoo builds from the deliveries.",
    )
    picking_count = fields.Integer(compute="_compute_picking_count")
    is_grouped = fields.Boolean(
        string="Grouped",
        compute="_compute_is_grouped",
        store=True,
    )

    transport_date = fields.Date(
        string="Transport date",
        required=True,
        tracking=True,
        default=fields.Date.context_today,
    )
    service_end_date = fields.Date(
        string="Service end date",
        tracking=True,
        help="Expected end date of the service. Public access to the document "
        f"is closed automatically {PUBLIC_ACCESS_DAYS} calendar days later "
        "(section Tercero.5).",
    )

    # --- (a) Contractual shipper ---
    shipper_id = fields.Many2one(
        "res.partner",
        string="Shipper",
        tracking=True,
        default=lambda self: self.env.company.partner_id,
    )
    shipper_vat = fields.Char(
        string="Shipper tax ID",
        related="shipper_id.vat",
        readonly=True,
    )
    shipper_address = fields.Char(
        string="Shipper address",
        compute="_compute_addresses",
    )

    # --- (b) Effective carrier ---
    carrier_id = fields.Many2one(
        "res.partner",
        string="Carrier",
        tracking=True,
        domain=[("deca_carrier", "=", True)],
    )
    carrier_vat = fields.Char(
        string="Carrier tax ID",
        related="carrier_id.vat",
        readonly=True,
    )
    carrier_address = fields.Char(
        string="Carrier address",
        compute="_compute_addresses",
    )
    carrier_authorization = fields.Char(
        string="Transport authorization",
        related="carrier_id.deca_authorization",
        readonly=False,
        store=True,
        help="Number of the carrier's transport card (MDP/MDL).",
    )

    # --- (g) Vehicle ---
    # The per-carrier domain and context live in the view: a model-level
    # `context` travels to the web client as a string and breaks `web_read`.
    tractor_plate_id = fields.Many2one(
        "l10n.es.deca.vehicle",
        string="Tractor plate",
        tracking=True,
    )
    trailer_plate_id = fields.Many2one(
        "l10n.es.deca.vehicle",
        string="Trailer plate",
        tracking=True,
    )

    # --- (c) (d) (f) Shipment ---
    line_ids = fields.One2many(
        "l10n.es.deca.line",
        "deca_id",
        string="Shipment",
        copy=False,
        readonly=True,
    )
    note = fields.Text(string="Notes")

    # --- Issuance and public access ---
    token = fields.Char(string="Public token", copy=False, readonly=True, index=True)
    public_url = fields.Char(
        string="Public URL",
        copy=False,
        readonly=True,
        help="URL frozen at issuance time: it is the one printed in the QR code "
        "of the PDF and it is never recomputed again.",
    )
    qr_image = fields.Binary(string="QR code", compute="_compute_qr_image")
    issue_date = fields.Datetime(string="Issue date", copy=False, readonly=True)
    access_close_date = fields.Date(
        string="Public access closing date",
        compute="_compute_access_close_date",
        store=True,
    )

    pdf_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Issued PDF",
        copy=False,
        readonly=True,
        ondelete="restrict",
    )

    # --- Own document supplied by the customer ---
    custom_pdf = fields.Binary(
        string="Document",
        attachment=True,
        copy=False,
        help="Your own document in PDF. The DeCA QR code is stamped on it and "
        "that stamped file becomes the document to be carried and the one the "
        "authority downloads, instead of the one Odoo generates.",
    )
    custom_pdf_filename = fields.Char(string="File name", copy=False)
    custom_pdf_page_count = fields.Integer(
        string="Pages",
        compute="_compute_custom_pdf_page_count",
    )
    qr_page = fields.Integer(
        string="QR page",
        default=1,
    )
    qr_position_x = fields.Float(
        string="QR horizontal position",
        default=72.0,
        help="Distance from the left edge, as a percentage of the page width.",
    )
    qr_position_y = fields.Float(
        string="QR vertical position",
        default=4.0,
        help="Distance from the top edge, as a percentage of the page height.",
    )
    qr_size = fields.Float(
        string="QR size",
        default=18.0,
        help="Side of the QR square, as a percentage of the page width.",
    )

    pdf_sha256 = fields.Char(
        string="PDF SHA-256",
        copy=False,
        readonly=True,
        help="Fingerprint of the PDF at the time of its issuance or last "
        "modification. It proves that the document has not been altered.",
    )

    change_ids = fields.One2many(
        "l10n.es.deca.change",
        "deca_id",
        string="Modification history",
        readonly=True,
    )
    access_log_ids = fields.One2many(
        "l10n.es.deca.access.log",
        "deca_id",
        string="Access log",
        readonly=True,
    )

    # --- Method B: reissuance ---
    replaced_deca_id = fields.Many2one(
        "l10n.es.deca",
        string="Replaces",
        copy=False,
        readonly=True,
        help="Original document replaced by this DeCA (Method B).",
    )
    replacement_deca_id = fields.Many2one(
        "l10n.es.deca",
        string="Replaced by",
        compute="_compute_replacement_deca_id",
    )
    reissue_reason = fields.Char(string="Reissuance reason", readonly=True)

    cancel_reason = fields.Char(string="Cancellation reason", readonly=True)
    cancel_date = fields.Datetime(string="Cancellation date", readonly=True)

    # --- Consistency with the deliveries ---
    lines_fingerprint = fields.Char(copy=False, readonly=True)
    pickings_changed = fields.Boolean(
        string="Deliveries changed after issuance",
        compute="_compute_pickings_changed",
    )
    missing_issue_data = fields.Char(
        string="Missing data",
        compute="_compute_missing_issue_data",
    )

    _sql_constraints = [
        ("token_unique", "UNIQUE(token)", "The DeCA token must be unique."),
    ]

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("picking_ids")
    def _compute_picking_count(self):
        for deca in self:
            deca.picking_count = len(deca.picking_ids)

    @api.depends("picking_ids")
    def _compute_is_grouped(self):
        for deca in self:
            deca.is_grouped = len(deca.picking_ids) > 1

    @api.depends("shipper_id", "carrier_id")
    def _compute_addresses(self):
        for deca in self:
            deca.shipper_address = deca._format_address(deca.shipper_id)
            deca.carrier_address = deca._format_address(deca.carrier_id)

    @api.depends("service_end_date")
    def _compute_access_close_date(self):
        for deca in self:
            if deca.service_end_date:
                deca.access_close_date = fields.Date.add(
                    deca.service_end_date, days=PUBLIC_ACCESS_DAYS
                )
            else:
                deca.access_close_date = False

    @api.depends("public_url")
    def _compute_qr_image(self):
        for deca in self:
            deca.qr_image = deca._build_qr_image(deca.public_url)

    @api.depends("custom_pdf")
    def _compute_custom_pdf_page_count(self):
        for deca in self:
            deca.custom_pdf_page_count = deca._read_custom_pdf_page_count()

    def _get_custom_pdf_bytes(self):
        """Return the uploaded PDF, immune to the ``bin_size`` context key.

        Form views read binary fields with ``bin_size`` enabled, which makes
        the field give back a human readable size instead of the content.
        """
        self.ensure_one()
        data = self.with_context(bin_size=False).custom_pdf
        return base64.b64decode(data) if data else b""

    def _read_custom_pdf_page_count(self):
        self.ensure_one()
        data = self._get_custom_pdf_bytes()
        if not data:
            return 0
        try:
            reader = PdfFileReader(io.BytesIO(data), strict=False)
            return reader.getNumPages()
        except Exception:
            return 0

    @api.constrains(
        "custom_pdf", "qr_page", "qr_position_x", "qr_position_y", "qr_size"
    )
    def _check_custom_pdf(self):
        for deca in self:
            if not deca.custom_pdf:
                continue
            pages = deca._read_custom_pdf_page_count()
            if not pages:
                raise ValidationError(
                    _(
                        "The file uploaded on DeCA %s is not a readable PDF.",
                        deca.name,
                    )
                )
            if len(deca._get_custom_pdf_bytes()) > MAX_PDF_BYTES:
                raise ValidationError(
                    _(
                        "The uploaded PDF exceeds the 5 MB limit set by section "
                        "Segundo.1 of the Resolution."
                    )
                )
            if not 1 <= deca.qr_page <= pages:
                raise ValidationError(
                    _(
                        "The QR code is placed on page %(page)s but the PDF only "
                        "has %(pages)s.",
                        page=deca.qr_page,
                        pages=pages,
                    )
                )
            if not 1.0 <= deca.qr_size <= 50.0:
                raise ValidationError(
                    _("The QR size must be between 1%% and 50%% of the page width.")
                )
            if not 0.0 <= deca.qr_position_x <= 100.0 or not (
                0.0 <= deca.qr_position_y <= 100.0
            ):
                raise ValidationError(_("The QR position must stay inside the page."))

    @api.depends("replaced_deca_id")
    def _compute_replacement_deca_id(self):
        replacements = self.env["l10n.es.deca"].search(
            [("replaced_deca_id", "in", self.ids)]
        )
        mapping = {r.replaced_deca_id.id: r for r in replacements}
        for deca in self:
            deca.replacement_deca_id = mapping.get(deca.id, False)

    @api.depends("lines_fingerprint", "picking_ids.move_ids.product_uom_qty")
    def _compute_pickings_changed(self):
        for deca in self:
            if deca.state in ("draft", "cancelled", "replaced") or not (
                deca.lines_fingerprint
            ):
                deca.pickings_changed = False
            else:
                deca.pickings_changed = (
                    deca._build_lines_fingerprint() != deca.lines_fingerprint
                )

    @api.depends(
        "state",
        "custom_pdf",
        "picking_ids",
        "line_ids",
        "shipper_id",
        "carrier_id",
        "service_end_date",
        "tractor_plate_id",
    )
    def _compute_missing_issue_data(self):
        for deca in self:
            if deca.state != "draft":
                deca.missing_issue_data = False
            else:
                deca.missing_issue_data = ", ".join(deca._get_missing_issue_data())

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains("picking_ids")
    def _check_pickings(self):
        for deca in self:
            if not deca.picking_ids:
                continue
            outgoing = deca.picking_ids.filtered(
                lambda p: p.picking_type_code != "outgoing"
            )
            if outgoing:
                raise ValidationError(
                    _(
                        "The DeCA is only issued for outgoing deliveries. A "
                        "receipt never generates a DeCA: that obligation belongs "
                        "to whoever ships the goods."
                    )
                )
            shippers = deca.picking_ids.mapped("company_id")
            if len(shippers) > 1 or shippers != deca.company_id:
                raise ValidationError(
                    _(
                        "All the deliveries of a DeCA must belong to the company "
                        "issuing it (%s).",
                        deca.company_id.display_name,
                    )
                )
            carriers = deca.picking_ids.mapped("deca_carrier_id")
            if len(carriers) > 1:
                raise ValidationError(
                    _(
                        "Only deliveries sharing shipper and carrier can be "
                        "grouped in the same DeCA (section Sexto.1). The selected "
                        "deliveries have different carriers: %s.",
                        ", ".join(carriers.mapped("display_name")),
                    )
                )
            conflicting = self.search(
                [
                    ("id", "!=", deca.id),
                    ("picking_ids", "in", deca.picking_ids.ids),
                    ("state", "not in", ("cancelled", "replaced")),
                ]
            )
            # A Method B draft coexists with the original document it replaces.
            conflicting -= deca.replaced_deca_id
            conflicting = conflicting.filtered(
                lambda d, deca=deca: d.replaced_deca_id != deca or d.state != "draft"
            )
            if conflicting:
                overlap = conflicting.picking_ids & deca.picking_ids
                raise ValidationError(
                    _(
                        "Deliveries %(pickings)s are already covered by DeCA "
                        "%(deca)s. A delivery cannot be covered by two active "
                        "DeCA at the same time.",
                        pickings=", ".join(overlap.mapped("name")),
                        deca=", ".join(conflicting.mapped("name")),
                    )
                )

    @api.constrains("carrier_id", "tractor_plate_id", "trailer_plate_id", "company_id")
    def _check_plates_belong_to_carrier(self):
        for deca in self:
            for plate, expected_type, label in (
                (deca.tractor_plate_id, "tractor", _("tractor unit")),
                (deca.trailer_plate_id, "trailer", _("trailer")),
            ):
                if not plate:
                    continue
                if plate.partner_id != deca.carrier_id:
                    raise ValidationError(
                        _(
                            "Plate %(plate)s does not belong to carrier %(carrier)s.",
                            plate=plate.name,
                            carrier=deca.carrier_id.display_name,
                        )
                    )
                if plate.vehicle_type != expected_type:
                    raise ValidationError(
                        _(
                            "Plate %(plate)s is not a %(label)s.",
                            plate=plate.name,
                            label=label,
                        )
                    )
                if plate.company_id and plate.company_id != deca.company_id:
                    raise ValidationError(
                        _(
                            "Plate %(plate)s belongs to company %(owner)s and "
                            "cannot be used in a DeCA of %(company)s.",
                            plate=plate.name,
                            owner=plate.company_id.display_name,
                            company=deca.company_id.display_name,
                        )
                    )

    @api.constrains("transport_date", "service_end_date")
    def _check_dates(self):
        for deca in self:
            if not deca.service_end_date:
                continue
            if deca.service_end_date < deca.transport_date:
                raise ValidationError(
                    _(
                        "The service end date cannot be earlier than the "
                        "transport date."
                    )
                )

    @api.constrains("name", "company_id", "state")
    def _check_name_unique(self):
        """Numbers must not repeat, but every draft shares the placeholder."""
        for deca in self:
            if deca.state == "draft":
                continue
            duplicate = self.search_count(
                [
                    ("name", "=", deca.name),
                    ("company_id", "=", deca.company_id.id),
                    ("state", "!=", "draft"),
                    ("id", "!=", deca.id),
                ]
            )
            if duplicate:
                raise ValidationError(
                    _("The DeCA number must be unique within each company.")
                )

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model
    def _get_sequence(self, company):
        """Return the company's own sequence, creating it on first use.

        This way every company numbers its DeCA independently, without sharing
        gaps with the rest.
        """
        sequence = (
            self.env["ir.sequence"]
            .sudo()
            .search(
                [("code", "=", "l10n.es.deca"), ("company_id", "=", company.id)],
                limit=1,
            )
        )
        if not sequence:
            sequence = (
                self.env["ir.sequence"]
                .sudo()
                .create(
                    {
                        "name": _("DeCA - %s", company.name),
                        "code": "l10n.es.deca",
                        "prefix": "DECA/%(year)s/",
                        "padding": 5,
                        "implementation": "no_gap",
                        "company_id": company.id,
                    }
                )
            )
        return sequence

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("service_end_date") and vals.get("transport_date"):
                vals["service_end_date"] = vals["transport_date"]
        decas = super().create(vals_list)
        decas._sync_lines()
        return decas

    def write(self, vals):
        if "picking_ids" in vals:
            frozen = self.filtered(lambda d: d.state != "draft")
            if frozen:
                raise UserError(
                    _(
                        "The deliveries of an already issued DeCA cannot be "
                        "changed (%s). Use 'Reissue DeCA' (Method B).",
                        ", ".join(frozen.mapped("name")),
                    )
                )
        result = super().write(vals)
        if "picking_ids" in vals:
            self._sync_lines()
        return result

    def unlink(self):
        issued = self.filtered(lambda d: d.state != "draft")
        if issued:
            # pylint: disable=no-raise-unlink
            raise UserError(
                _(
                    "An issued DeCA must be kept for at least one year and cannot "
                    "be deleted (%s).",
                    ", ".join(issued.mapped("name")),
                )
            )
        return super().unlink()

    @api.onchange("carrier_id")
    def _onchange_carrier_id(self):
        if self.tractor_plate_id.partner_id != self.carrier_id:
            self.tractor_plate_id = False
        if self.trailer_plate_id.partner_id != self.carrier_id:
            self.trailer_plate_id = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _format_address(self, partner, include_country=True):
        if not partner:
            return ""
        parts = [
            partner.display_name,
            partner.street,
            partner.street2,
            " ".join(filter(None, [partner.zip, partner.city])),
            partner.state_id.name,
        ]
        if include_country:
            parts.append(partner.country_id.name)
        return ", ".join(part.strip() for part in parts if part and part.strip())

    @api.model
    def _build_qr_image(self, url):
        if not url or qrcode is None:
            return False
        code = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=6,
            border=2,
        )
        code.add_data(url)
        code.make(fit=True)
        stream = io.BytesIO()
        code.make_image(fill_color="black", back_color="white").save(
            stream, format="PNG"
        )
        return base64.b64encode(stream.getvalue())

    def _prepare_line_vals(self, picking, move):
        return {
            "deca_id": self.id,
            "picking_id": picking.id,
            "origin_address": self._format_address(
                picking.location_id.warehouse_id.partner_id
                or picking.company_id.partner_id,
                include_country=False,
            ),
            "destination_address": self._format_address(
                picking.partner_id, include_country=False
            ),
            "transport_date": (
                picking.scheduled_date and picking.scheduled_date.date()
            ),
            "product_id": move.product_id.id,
            "nature": move.product_id.display_name,
            "quantity": move.product_uom_qty,
            "product_uom_id": move.product_uom.id,
            "weight": move.product_id.weight * move.product_uom_qty,
        }

    def _sync_lines(self):
        """Rebuild the shipment lines from the linked deliveries.

        The lines mirror the delivery: any change is made on the delivery
        itself, never on the DeCA.
        """
        Line = self.env["l10n.es.deca.line"]
        for deca in self:
            if deca.state != "draft":
                continue
            deca.line_ids.unlink()
            vals_list = []
            for picking in deca.picking_ids:
                for move in picking.move_ids:
                    vals_list.append(deca._prepare_line_vals(picking, move))
            if vals_list:
                Line.create(vals_list)
            deca.lines_fingerprint = deca._build_lines_fingerprint()
        return True

    def _build_lines_fingerprint(self):
        """Fingerprint of the delivery contents, used to detect changes."""
        self.ensure_one()
        payload = []
        for picking in self.picking_ids.sorted("id"):
            for move in picking.move_ids.sorted("id"):
                payload.append(
                    f"{picking.id}|{move.product_id.id}"
                    f"|{move.product_uom_qty}|{move.product_uom.id}"
                )
        return hashlib.sha256("\n".join(payload).encode()).hexdigest()

    def _get_public_base_url(self):
        """Domain from which this company's DeCA are served.

        By default it is the instance's own domain (``web.base.url``), which is
        what answers ``/deca/<token>``. The "DeCA public domain" setting is only
        needed when a reverse proxy publishes this company's documents under a
        different domain name.
        """
        self.ensure_one()
        domain = (self.company_id.deca_public_domain or "").strip()
        if domain:
            domain = domain.rstrip("/")
            if "://" in domain:
                domain = domain.split("://", 1)[1]
            # Section Tercero.1: the service is always published over HTTPS.
            return f"https://{domain}"
        base_url = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        )
        return base_url.rstrip("/")

    def _build_public_url(self, token):
        self.ensure_one()
        return f"{self._get_public_base_url()}/deca/{token}"

    def _render_pdf(self):
        self.ensure_one()
        if self.custom_pdf:
            pdf = self._stamp_qr_on_custom_pdf()
        else:
            pdf, _content_type = self.env["ir.actions.report"]._render_qweb_pdf(
                "l10n_es_deca.action_report_deca", res_ids=self.ids
            )
        if len(pdf) > MAX_PDF_BYTES:
            raise UserError(
                _(
                    "The generated PDF takes %(size).2f MB and exceeds the 5 MB "
                    "limit set by section Segundo.1 of the Resolution.",
                    size=len(pdf) / (1024 * 1024),
                )
            )
        return pdf

    def _build_qr_overlay(self, media_box):
        """One-page PDF holding just the QR, ready to be merged on a page."""
        self.ensure_one()
        width = float(media_box.getWidth())
        height = float(media_box.getHeight())
        side = self.qr_size / 100.0 * width
        # Coordinates travel as a top-left offset; reportlab draws bottom-up.
        pos_x = self.qr_position_x / 100.0 * width
        pos_y = height - (self.qr_position_y / 100.0 * height) - side
        qr_png = base64.b64decode(
            self._build_qr_image(self.public_url or self._build_public_url("preview"))
        )
        stream = io.BytesIO()
        overlay = canvas.Canvas(stream, pagesize=(width, height))
        overlay.drawImage(
            ImageReader(io.BytesIO(qr_png)),
            pos_x,
            pos_y,
            width=side,
            height=side,
            mask="auto",
        )
        overlay.save()
        stream.seek(0)
        return PdfFileReader(stream, strict=False).getPage(0)

    def _stamp_qr_on_custom_pdf(self):
        """Return the customer's own PDF with the DeCA QR code stamped on it."""
        self.ensure_one()
        if canvas is None or qrcode is None:
            raise UserError(
                _(
                    "The python libraries 'reportlab' and 'qrcode' are required "
                    "to stamp the QR code on your own document."
                )
            )
        reader = PdfFileReader(io.BytesIO(self._get_custom_pdf_bytes()), strict=False)
        writer = PdfFileWriter()
        target = max(self.qr_page, 1) - 1
        for index in range(reader.getNumPages()):
            page = reader.getPage(index)
            if index == target:
                page.mergePage(self._build_qr_overlay(page.mediaBox))
            writer.addPage(page)
        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()

    def _store_pdf(self):
        """Render the PDF, archive it and update its SHA-256 fingerprint."""
        self.ensure_one()
        pdf = self._render_pdf()
        filename = f"{self.name.replace('/', '_')}.pdf"
        attachment_vals = {
            "name": filename,
            "datas": base64.b64encode(pdf),
            "mimetype": "application/pdf",
            "res_model": self._name,
            "res_id": self.id,
        }
        if self.pdf_attachment_id:
            self.pdf_attachment_id.sudo().write(attachment_vals)
        else:
            attachment = self.env["ir.attachment"].sudo().create(attachment_vals)
            self.pdf_attachment_id = attachment.id
        self.pdf_sha256 = hashlib.sha256(pdf).hexdigest()
        return self.pdf_attachment_id

    def _get_missing_issue_data(self):
        """Labels of the data still needed to issue the document.

        Nothing is enforced while the DeCA is a draft: it has to be possible to
        save it and come back later, exactly like a draft invoice.
        """
        self.ensure_one()
        # Your own document is already a complete delivery note, so the data
        # Odoo would print is pointless: nothing is enforced for it.
        if self.custom_pdf:
            return []
        missing = []
        if not self.picking_ids:
            missing.append(_("Deliveries"))
        if not self.line_ids:
            missing.append(_("Nature and weight of the goods"))
        if not self.shipper_id:
            missing.append(_("Shipper"))
        if not self.carrier_id:
            missing.append(_("Carrier"))
        if not self.service_end_date:
            missing.append(_("Service end date"))
        if not self.tractor_plate_id:
            missing.append(_("Tractor plate"))
        return missing

    def _check_issue_ready(self):
        self.ensure_one()
        missing = self._get_missing_issue_data()
        if missing:
            raise UserError(
                _("Mandatory data missing to issue the DeCA: %s.", ", ".join(missing))
            )
        for partner, label in (
            (self.shipper_id, _("shipper")),
            (self.carrier_id, _("carrier")),
        ):
            if not partner:
                continue
            if not partner.vat:
                raise UserError(
                    _(
                        "The %(label)s %(partner)s has no tax ID set.",
                        label=label,
                        partner=partner.display_name,
                    )
                )
            if not check_spanish_vat(partner.vat):
                raise UserError(
                    _(
                        "Tax ID %(vat)s of the %(label)s %(partner)s does not pass "
                        "the check digit validation.",
                        vat=partner.vat,
                        label=label,
                        partner=partner.display_name,
                    )
                )
        if not self._get_public_base_url():
            raise UserError(
                _(
                    "There is no public domain to serve the DeCA of company %s "
                    "from. Set the web.base.url parameter or the DeCA public "
                    "domain before issuing: otherwise the QR code of the PDF "
                    "would point to an invalid URL.",
                    self.company_id.display_name,
                )
            )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_issue(self):
        for deca in self:
            if deca.state != "draft":
                raise UserError(
                    _("DeCA %s has already been issued.", deca.name),
                )
            deca._check_issue_ready()
            deca.write(
                {
                    "name": deca._get_sequence(deca.company_id).next_by_id(),
                    "token": secrets.token_urlsafe(TOKEN_BYTES),
                    "state": "issued",
                    "issue_date": fields.Datetime.now(),
                }
            )
            # The URL is frozen here: it is the one printed in the PDF QR code.
            deca.public_url = deca._build_public_url(deca.token)
            deca.lines_fingerprint = deca._build_lines_fingerprint()
            deca._store_pdf()
            deca.message_post(
                body=_(
                    "DeCA issued. SHA-256: %(hash)s. Public URL: %(url)s",
                    hash=deca.pdf_sha256,
                    url=deca.public_url,
                )
            )

            if deca.replaced_deca_id:
                # Method B: the original is kept untouched, only flagged.
                deca.replaced_deca_id.state = "replaced"
                deca.replaced_deca_id.message_post(
                    body=_(
                        "Replaced by %(new)s (Method B). This document is kept "
                        "untouched for traceability purposes and its public link "
                        "redirects to the document in force.",
                        new=deca.name,
                    )
                )
            deca._send_issue_email()
        return True

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        company = self.env.company
        for fname, company_fname in (
            ("qr_page", "deca_qr_page"),
            ("qr_position_x", "deca_qr_position_x"),
            ("qr_position_y", "deca_qr_position_y"),
            ("qr_size", "deca_qr_size"),
        ):
            if fname in fields_list and company[company_fname]:
                values[fname] = company[company_fname]
        return values

    def action_upload_own_document(self):
        """Open the dialog that turns your own document into the DeCA."""
        self.ensure_one()
        if self.state != "draft":
            raise UserError(
                _("Your own document can only be attached while the DeCA is a draft.")
            )
        return {
            "type": "ir.actions.act_window",
            "res_model": "l10n.es.deca.own.document",
            "name": _("Convert document to DeCA"),
            "view_mode": "form",
            "target": "new",
            "context": {"default_deca_id": self.id},
        }

    def action_configure_qr(self):
        """Open the viewer where the QR is dragged onto the uploaded PDF."""
        self.ensure_one()
        if not self.custom_pdf:
            raise UserError(_("Upload your own document before placing the QR code."))
        return {
            "type": "ir.actions.client",
            "tag": "l10n_es_deca_qr_configure",
            "name": _("Place the QR code"),
            "params": {"res_model": self._name, "res_id": self.id},
        }

    def get_qr_placement_info(self):
        """Placement data consumed by the QR configurator."""
        self.ensure_one()
        return {
            "name": self.name,
            "editable": self.state == "draft",
            "page_count": self.custom_pdf_page_count,
            "page": self.qr_page,
            "position_x": self.qr_position_x,
            "position_y": self.qr_position_y,
            "size": self.qr_size,
        }

    def set_qr_placement(self, placement):
        """Persist the placement chosen in the configurator."""
        self.ensure_one()
        if self.state != "draft":
            raise UserError(
                _("The QR code can only be moved while the DeCA is a draft.")
            )
        self.write(
            {
                "qr_page": int(placement["page"]),
                "qr_position_x": float(placement["position_x"]),
                "qr_position_y": float(placement["position_y"]),
                "qr_size": float(placement["size"]),
            }
        )
        return self.get_qr_placement_info()

    def action_preview_stamped_pdf(self):
        """Download the own document with the QR already stamped, before issuing."""
        self.ensure_one()
        if not self.custom_pdf:
            raise UserError(_("Upload your own document first."))
        attachment = (
            self.env["ir.attachment"]
            .sudo()
            .create(
                {
                    "name": _("QR preview - %s.pdf", self.name),
                    "datas": base64.b64encode(self._stamp_qr_on_custom_pdf()),
                    "mimetype": "application/pdf",
                    "res_model": self._name,
                    "res_id": self.id,
                }
            )
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

    def _send_issue_email(self):
        template = self.env.ref(
            "l10n_es_deca.mail_template_deca_issued", raise_if_not_found=False
        )
        if not template:
            return False
        recipients = (self.shipper_id | self.carrier_id).filtered("email")
        if not recipients:
            return False
        # Recipients travel as partners so the chatter records who was notified.
        template.send_mail(self.id, force_send=False)
        self.message_post(
            body=_("DeCA sent by email to: %s", ", ".join(recipients.mapped("email")))
        )
        return True

    def action_send_email(self):
        self.ensure_one()
        template = self.env.ref(
            "l10n_es_deca.mail_template_deca_issued", raise_if_not_found=False
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_model": self._name,
                "default_res_ids": self.ids,
                "default_template_id": template.id if template else False,
                "default_composition_mode": "comment",
            },
        }

    def action_register_modification(self):
        """Method A (section Quinto.1): correction on the same token and URL."""
        self.ensure_one()
        if self.state not in ("issued", "modified"):
            raise UserError(
                _("Only an issued or already modified DeCA can be modified.")
            )
        return {
            "type": "ir.actions.act_window",
            "res_model": "l10n.es.deca.modify.wizard",
            "view_mode": "form",
            "target": "new",
            "name": _("Register DeCA modification"),
            "context": {"default_deca_id": self.id},
        }

    def action_reissue(self):
        """Method B (section Quinto.2): new document with its own token and QR."""
        self.ensure_one()
        if self.state not in ("issued", "modified"):
            raise UserError(_("Only an issued DeCA can be reissued."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "l10n.es.deca.reissue.wizard",
            "view_mode": "form",
            "target": "new",
            "name": _("Reissue DeCA"),
            "context": {"default_deca_id": self.id},
        }

    def action_cancel(self):
        self.ensure_one()
        if not self.env.user.has_group("l10n_es_deca.group_deca_manager"):
            raise AccessError(_("Only a DeCA Administrator can cancel a document."))
        if self.state not in ("issued", "modified"):
            raise UserError(_("Only an issued DeCA can be cancelled."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "l10n.es.deca.cancel.wizard",
            "view_mode": "form",
            "target": "new",
            "name": _("Cancel DeCA"),
            "context": {"default_deca_id": self.id},
        }

    def action_verify_integrity(self):
        self.ensure_one()
        if not self.pdf_attachment_id or not self.pdf_sha256:
            raise UserError(_("This DeCA has no issued PDF yet."))
        stored = base64.b64decode(self.pdf_attachment_id.sudo().datas or b"")
        current_hash = hashlib.sha256(stored).hexdigest()
        if current_hash == self.pdf_sha256:
            message = _(
                "Integrity verified: the archived PDF matches exactly the SHA-256 "
                "fingerprint recorded at issuance time."
            )
            sticky = False
            msg_type = "success"
        else:
            message = _(
                "Warning! The archived PDF does NOT match the recorded fingerprint "
                "(expected %(expected)s, got %(current)s).",
                expected=self.pdf_sha256,
                current=current_hash,
            )
            sticky = True
            msg_type = "danger"
        self.message_post(body=message)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Integrity check"),
                "message": message,
                "type": msg_type,
                "sticky": sticky,
            },
        }

    def action_open_pdf(self):
        self.ensure_one()
        if not self.pdf_attachment_id:
            raise UserError(_("This DeCA has no issued PDF yet."))
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{self.pdf_attachment_id.id}?download=true",
            "target": "self",
        }

    def action_view_pickings(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "stock.action_picking_tree_all"
        )
        action["domain"] = [("id", "in", self.picking_ids.ids)]
        if len(self.picking_ids) == 1:
            action["view_mode"] = "form"
            action["views"] = [(False, "form")]
            action["res_id"] = self.picking_ids.id
        return action

    def action_open_replacement(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.replacement_deca_id.id,
        }

    def action_open_replaced(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.replaced_deca_id.id,
        }

    def action_refresh_from_pickings(self):
        self.ensure_one()
        self._sync_lines()
        return True

    # ------------------------------------------------------------------
    # Public access
    # ------------------------------------------------------------------
    def _is_public_access_open(self):
        self.ensure_one()
        return self.state in ("issued", "modified") and bool(self.pdf_attachment_id)

    def _log_public_access(self, ip_address, method, status_code, user_agent=None):
        self.ensure_one()
        self.env["l10n.es.deca.access.log"].sudo().create(
            {
                "deca_id": self.id,
                "ip_address": ip_address,
                "method": method,
                "status_code": status_code,
                "user_agent": (user_agent or "")[:255],
            }
        )

    @api.model
    def _cron_close_public_access(self):
        """Section Tercero.5: close the public download after 7 calendar days."""
        today = fields.Date.context_today(self)
        expired = self.sudo().search(
            [
                ("state", "in", ("issued", "modified")),
                ("access_close_date", "<", today),
            ]
        )
        for deca in expired:
            deca.state = "closed"
            deca.message_post(
                body=_(
                    "Public access closed automatically: %s calendar days have "
                    "elapsed since the end of the service (section Tercero.5). "
                    "The document is kept indefinitely.",
                    PUBLIC_ACCESS_DAYS,
                )
            )
        return True
