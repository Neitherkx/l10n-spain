# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import io

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import tagged
from odoo.tools.pdf import PdfFileReader

from .common import DecaCommon


def build_pdf(pages=3):
    """A minimal multi-page PDF standing in for the customer's own file."""
    from reportlab.pdfgen import canvas

    stream = io.BytesIO()
    document = canvas.Canvas(stream)
    for page in range(pages):
        document.drawString(72, 750, "Own delivery note - page %s" % (page + 1))
        document.showPage()
    document.save()
    return stream.getvalue()


@tagged("post_install", "-at_install")
class TestDecaCustomPdf(DecaCommon):
    def setUp(self):
        super().setUp()
        self.deca = self._create_deca()
        self.own_pdf = build_pdf()

    def _upload(self, pdf=None):
        self.deca.write(
            {
                "custom_pdf": base64.b64encode(pdf or self.own_pdf),
                "custom_pdf_filename": "own.pdf",
            }
        )
        return self.deca

    def test_page_count(self):
        self.assertEqual(self.deca.custom_pdf_page_count, 0)
        self._upload()
        self.assertEqual(self.deca.custom_pdf_page_count, 3)

    def test_page_count_survives_a_form_read(self):
        """Form views read binary fields as a size, not as content."""
        self._upload()
        self.deca.invalidate_recordset()
        deca = self.deca.with_context(bin_size=True)
        self.assertEqual(deca.custom_pdf_page_count, 3)

    def test_default_placement_comes_from_company(self):
        self.company.write(
            {
                "deca_qr_page": 2,
                "deca_qr_position_x": 10.0,
                "deca_qr_position_y": 20.0,
                "deca_qr_size": 30.0,
            }
        )
        defaults = (
            self.env["l10n.es.deca"]
            .with_company(self.company)
            .default_get(["qr_page", "qr_position_x", "qr_position_y", "qr_size"])
        )
        self.assertEqual(defaults["qr_page"], 2)
        self.assertEqual(defaults["qr_position_x"], 10.0)
        self.assertEqual(defaults["qr_position_y"], 20.0)
        self.assertEqual(defaults["qr_size"], 30.0)

    def test_stamp_keeps_every_page(self):
        self._upload()
        self.deca.qr_page = 2
        stamped = self.deca._stamp_qr_on_custom_pdf()
        reader = PdfFileReader(io.BytesIO(stamped), strict=False)
        self.assertEqual(reader.getNumPages(), 3)
        self.assertGreater(len(stamped), 0)

    def test_issue_stores_the_stamped_own_pdf(self):
        self._upload()
        self.deca.action_issue()
        stored = base64.b64decode(self.deca.pdf_attachment_id.datas)
        reader = PdfFileReader(io.BytesIO(stored), strict=False)
        # The Odoo report is a single page, the customer's file has three.
        self.assertEqual(reader.getNumPages(), 3)
        self.assertTrue(self.deca.pdf_sha256)

    def test_issue_without_own_pdf_uses_the_odoo_report(self):
        self.deca.action_issue()
        self.assertTrue(self.deca.pdf_attachment_id)
        self.assertTrue(self.deca.pdf_sha256)

    def test_invalid_pdf_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._upload(pdf=b"this is not a pdf")

    def test_qr_page_out_of_range(self):
        self._upload()
        with self.assertRaises(ValidationError):
            self.deca.qr_page = 9

    def test_qr_size_out_of_range(self):
        self._upload()
        with self.assertRaises(ValidationError):
            self.deca.qr_size = 80.0

    def test_configure_requires_a_file(self):
        with self.assertRaises(UserError):
            self.deca.action_configure_qr()
        self._upload()
        action = self.deca.action_configure_qr()
        self.assertEqual(action["tag"], "l10n_es_deca_qr_configure")
        self.assertEqual(action["params"]["res_id"], self.deca.id)

    def test_placement_round_trip(self):
        self._upload()
        info = self.deca.set_qr_placement(
            {"page": 3, "position_x": 12.5, "position_y": 80.0, "size": 25.0}
        )
        self.assertEqual(info["page"], 3)
        self.assertEqual(info["position_x"], 12.5)
        self.assertEqual(info["position_y"], 80.0)
        self.assertEqual(info["size"], 25.0)
        self.assertEqual(info["page_count"], 3)
        self.assertTrue(info["editable"])

    def test_placement_is_frozen_once_issued(self):
        self._upload()
        self.deca.action_issue()
        self.assertFalse(self.deca.get_qr_placement_info()["editable"])
        with self.assertRaises(UserError):
            self.deca.set_qr_placement(
                {"page": 1, "position_x": 0.0, "position_y": 0.0, "size": 10.0}
            )

    def test_preview_requires_a_file(self):
        with self.assertRaises(UserError):
            self.deca.action_preview_stamped_pdf()
        self._upload()
        action = self.deca.action_preview_stamped_pdf()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertIn("download=true", action["url"])

    def test_own_document_stands_without_deliveries(self):
        """Your own document already details the shipment, so it stands alone."""
        self.deca.picking_ids = [fields.Command.clear()]
        with self.assertRaises(UserError):
            self.deca.action_issue()
        self._upload()
        self.deca.action_issue()
        self.assertEqual(self.deca.state, "issued")
        self.assertFalse(self.deca.picking_ids)

    def test_wizard_stores_the_document_and_opens_the_placer(self):
        wizard = (
            self.env["l10n.es.deca.own.document"]
            .with_context(**self.deca.action_upload_own_document()["context"])
            .create(
                {
                    "document": base64.b64encode(self.own_pdf),
                    "document_filename": "albaran.pdf",
                }
            )
        )
        self.assertEqual(wizard.deca_id, self.deca)
        action = wizard.action_confirm()
        self.assertEqual(action["tag"], "l10n_es_deca_qr_configure")
        self.assertEqual(self.deca.custom_pdf_filename, "albaran.pdf")
        self.assertEqual(self.deca.custom_pdf_page_count, 3)

    def test_wizard_refuses_an_issued_deca(self):
        self._upload()
        self.deca.action_issue()
        with self.assertRaises(UserError):
            self.deca.action_upload_own_document()
