# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import tagged

from .common import DecaCommon


@tagged("post_install", "-at_install")
class TestDecaMethods(DecaCommon):
    """Methods A and B of the Resolution, and cancellation."""

    def _modify(self, deca, **kwargs):
        wizard = self.env["l10n.es.deca.modify.wizard"].create(
            dict({"deca_id": deca.id, "reason": "Tractor unit breakdown"}, **kwargs)
        )
        return wizard.action_apply()

    # --- Method A ---------------------------------------------------
    def test_method_a_keeps_token_url_and_qr(self):
        deca = self._create_deca()
        deca.action_issue()
        token, url, old_hash = deca.token, deca.public_url, deca.pdf_sha256
        attachment = deca.pdf_attachment_id

        self._modify(
            deca,
            field_name="tractor_plate_id",
            new_tractor_plate_id=self.tractor_spare.id,
        )

        self.assertEqual(deca.state, "modified")
        self.assertEqual(deca.token, token)
        self.assertEqual(deca.public_url, url)
        self.assertEqual(deca.pdf_attachment_id, attachment)
        self.assertNotEqual(deca.pdf_sha256, old_hash)
        self.assertEqual(deca.tractor_plate_id, self.tractor_spare)

    def test_method_a_records_change_history(self):
        deca = self._create_deca()
        deca.action_issue()
        self._modify(
            deca,
            field_name="tractor_plate_id",
            new_tractor_plate_id=self.tractor_spare.id,
        )
        change = deca.change_ids
        self.assertEqual(len(change), 1)
        self.assertEqual(change.field_label, "Tractor plate")
        self.assertIn("1234 ABC", change.old_value)
        self.assertIn("5678 DEF", change.new_value)
        self.assertEqual(change.reason, "Tractor unit breakdown")
        self.assertEqual(change.user_id, self.env.user)

    def test_method_a_on_note_and_dates(self):
        deca = self._create_deca()
        deca.action_issue()
        self._modify(deca, field_name="note", new_note="Fragile goods")
        self.assertEqual(deca.note, "Fragile goods")
        new_end = fields.Date.add(deca.service_end_date, days=2)
        self._modify(deca, field_name="service_end_date", new_service_end_date=new_end)
        self.assertEqual(deca.service_end_date, new_end)
        self.assertEqual(len(deca.change_ids), 2)

    def test_method_a_rejects_same_value(self):
        deca = self._create_deca()
        deca.action_issue()
        with self.assertRaises(UserError):
            self._modify(
                deca,
                field_name="tractor_plate_id",
                new_tractor_plate_id=self.tractor.id,
            )

    def test_method_a_requires_issued_deca(self):
        deca = self._create_deca()
        with self.assertRaises(UserError):
            self._modify(
                deca,
                field_name="tractor_plate_id",
                new_tractor_plate_id=self.tractor_spare.id,
            )

    def test_method_a_change_appears_in_pdf(self):
        deca = self._create_deca()
        deca.action_issue()
        self._modify(
            deca,
            field_name="tractor_plate_id",
            new_tractor_plate_id=self.tractor_spare.id,
        )
        html = (
            self.env["ir.actions.report"]
            ._render_qweb_html("l10n_es_deca.action_report_deca", deca.ids)[0]
            .decode()
        )
        self.assertIn("Modification history", html)
        self.assertIn("Tractor unit breakdown", html)

    # --- Method B ---------------------------------------------------
    def _reissue(self, deca, reason="The shipper changes"):
        wizard = self.env["l10n.es.deca.reissue.wizard"].create(
            {"deca_id": deca.id, "reason": reason}
        )
        action = wizard.action_reissue()
        return self.env["l10n.es.deca"].browse(action["res_id"])

    def test_method_b_creates_new_draft_sharing_pickings(self):
        deca = self._create_deca()
        deca.action_issue()
        new_deca = self._reissue(deca)
        self.assertEqual(new_deca.state, "draft")
        self.assertEqual(new_deca.replaced_deca_id, deca)
        self.assertEqual(new_deca.picking_ids, deca.picking_ids)
        self.assertFalse(new_deca.token)
        self.assertEqual(deca.replacement_deca_id, new_deca)
        # El original sigue vigente hasta que se emita el sustituto.
        self.assertEqual(deca.state, "issued")

    def test_method_b_issue_marks_original_as_replaced(self):
        deca = self._create_deca()
        deca.action_issue()
        old_token, old_hash = deca.token, deca.pdf_sha256
        new_deca = self._reissue(deca)
        new_deca.action_issue()

        self.assertEqual(deca.state, "replaced")
        self.assertEqual(new_deca.state, "issued")
        self.assertNotEqual(new_deca.token, old_token)
        self.assertNotEqual(new_deca.public_url, deca.public_url)
        self.assertNotEqual(new_deca.pdf_sha256, old_hash)
        # El documento original se conserva intacto.
        self.assertEqual(deca.token, old_token)
        self.assertEqual(deca.pdf_sha256, old_hash)
        self.assertTrue(deca.pdf_attachment_id)

    def test_method_b_picking_points_to_new_deca(self):
        deca = self._create_deca()
        picking = deca.picking_ids
        deca.action_issue()
        new_deca = self._reissue(deca)
        new_deca.action_issue()
        self.assertEqual(picking.deca_id, new_deca)

    def test_method_b_twice_is_blocked(self):
        deca = self._create_deca()
        deca.action_issue()
        self._reissue(deca)
        with self.assertRaises(UserError):
            self._reissue(deca)

    # --- Cancellation ------------------------------------------------
    def _cancel(self, deca, reason="The customer cancels the order"):
        wizard = self.env["l10n.es.deca.cancel.wizard"].create(
            {"deca_id": deca.id, "reason": reason}
        )
        return wizard.action_cancel()

    def test_cancel_future_service(self):
        future = fields.Date.add(self.today, days=5)
        deca = self._create_deca(transport_date=future, service_end_date=future)
        deca.action_issue()
        self._cancel(deca)
        self.assertEqual(deca.state, "cancelled")
        self.assertEqual(deca.cancel_reason, "The customer cancels the order")
        self.assertTrue(deca.cancel_date)
        # The PDF and the token are kept, but the link stops serving it.
        self.assertTrue(deca.pdf_attachment_id)
        self.assertTrue(deca.token)
        self.assertFalse(deca._is_public_access_open())

    def test_cancel_started_service_is_blocked(self):
        deca = self._create_deca()
        deca.action_issue()
        with self.assertRaises(UserError):
            self._cancel(deca)

    def test_cancel_requires_manager(self):
        future = fields.Date.add(self.today, days=5)
        deca = self._create_deca(transport_date=future, service_end_date=future)
        deca.action_issue()
        user = self.env["res.users"].create(
            {
                "name": "DeCA Operator",
                "login": "deca_user_test",
                "groups_id": [
                    fields.Command.set(
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("stock.group_stock_user").id,
                            self.env.ref("l10n_es_deca.group_deca_user").id,
                        ]
                    )
                ],
            }
        )
        with self.assertRaises(AccessError):
            self.env["l10n.es.deca.cancel.wizard"].with_user(user).create(
                {"deca_id": deca.id, "reason": "Should not be allowed"}
            ).action_cancel()

    def test_cancelled_picking_can_get_a_new_deca(self):
        future = fields.Date.add(self.today, days=5)
        picking = self._create_picking()
        deca = self._create_deca(
            picking, transport_date=future, service_end_date=future
        )
        deca.action_issue()
        self._cancel(deca)
        self.assertFalse(picking.deca_id)
        new_deca = self._create_deca(picking)
        self.assertEqual(picking.deca_id, new_deca)
