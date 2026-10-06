# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64

from odoo import fields
from odoo.tests.common import HttpCase, tagged

from .common import DecaCommon


@tagged("post_install", "-at_install")
class TestDecaPublicAccess(HttpCase, DecaCommon):
    """Section Tercero: the public link serves the PDF without login nor interaction."""

    def _get(self, token):
        return self.url_open(f"/deca/{token}", allow_redirects=False)

    def test_public_download_serves_the_pdf(self):
        deca = self._create_deca()
        deca.action_issue()
        response = self._get(deca.token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/pdf")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn("inline", response.headers["Content-Disposition"])
        self.assertIn(
            deca.name.replace("/", "_"), response.headers["Content-Disposition"]
        )
        self.assertEqual(
            response.content,
            base64.b64decode(deca.pdf_attachment_id.datas),
        )

    def test_public_download_is_logged(self):
        deca = self._create_deca()
        deca.action_issue()
        self._get(deca.token)
        deca.invalidate_recordset(["access_log_ids"])
        log = deca.access_log_ids
        self.assertEqual(len(log), 1)
        self.assertEqual(log.status_code, 200)
        self.assertEqual(log.method, "GET")
        self.assertTrue(log.ip_address)

    def test_unknown_token_is_not_found(self):
        self.assertEqual(self._get("no-existe").status_code, 404)

    def test_draft_deca_is_not_found(self):
        deca = self._create_deca()
        deca.token = "tokenborradordeprueba1"
        deca.flush_recordset()
        self.assertEqual(self._get(deca.token).status_code, 404)

    def test_cancelled_deca_returns_gone(self):
        future = fields.Date.add(self.today, days=5)
        deca = self._create_deca(transport_date=future, service_end_date=future)
        deca.action_issue()
        self.env["l10n.es.deca.cancel.wizard"].create(
            {"deca_id": deca.id, "reason": "Anulado"}
        ).action_cancel()
        deca.flush_recordset()
        response = self._get(deca.token)
        self.assertEqual(response.status_code, 410)
        self.assertIn("cancelled", response.text)

    def test_replaced_deca_points_to_the_new_one(self):
        deca = self._create_deca()
        deca.action_issue()
        action = (
            self.env["l10n.es.deca.reissue.wizard"]
            .create({"deca_id": deca.id, "reason": "The shipper changes"})
            .action_reissue()
        )
        new_deca = self.env["l10n.es.deca"].browse(action["res_id"])
        new_deca.action_issue()
        self.env.flush_all()

        response = self._get(deca.token)
        self.assertEqual(response.status_code, 410)
        self.assertIn(new_deca.public_url, response.text)

        self.assertEqual(self._get(new_deca.token).status_code, 200)

    def test_closed_deca_returns_gone(self):
        past = fields.Date.add(self.today, days=-30)
        deca = self._create_deca(transport_date=past, service_end_date=past)
        deca.action_issue()
        self.env["l10n.es.deca"]._cron_close_public_access()
        self.env.flush_all()
        response = self._get(deca.token)
        self.assertEqual(response.status_code, 410)
        self.assertIn("seven calendar days", response.text)
