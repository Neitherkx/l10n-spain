# Copyright 2026 Grupo Isonor - David Palanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import hashlib

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import tagged
from odoo.tools import mute_logger

from .common import DecaCommon


@tagged("post_install", "-at_install")
class TestDecaDocument(DecaCommon):
    def test_lines_are_built_and_the_number_waits_for_the_issue(self):
        picking = self._create_picking()
        deca = self._create_deca(picking)
        self.assertNotIn("DECA/", deca.name)
        self.assertEqual(deca.state, "draft")
        self.assertEqual(len(deca.line_ids), 1)
        line = deca.line_ids
        self.assertEqual(line.picking_id, picking)
        self.assertEqual(line.product_id, self.product)
        self.assertEqual(line.quantity, 10.0)
        self.assertEqual(line.weight, 250.0)
        self.assertIn("Valencia", line.destination_address)
        self.assertFalse(deca.is_grouped)
        self.assertEqual(deca.picking_count, 1)

    def test_grouped_deca(self):
        pickings = self._create_picking() | self._create_picking()
        deca = self._create_deca(pickings)
        self.assertTrue(deca.is_grouped)
        self.assertEqual(deca.picking_count, 2)
        self.assertEqual(len(deca.line_ids), 2)

    def test_access_close_date(self):
        deca = self._create_deca()
        self.assertEqual(
            deca.access_close_date, fields.Date.add(deca.service_end_date, days=7)
        )

    def test_issue_generates_token_url_pdf_and_hash(self):
        deca = self._create_deca()
        deca.action_issue()
        self.assertEqual(deca.state, "issued")
        self.assertTrue(deca.issue_date)
        self.assertEqual(len(deca.token), 22)
        self.assertEqual(
            deca.public_url, f"https://deca.test.example/deca/{deca.token}"
        )
        self.assertTrue(deca.pdf_attachment_id)
        self.assertEqual(deca.pdf_attachment_id.mimetype, "application/pdf")
        # Odoo does not call wkhtmltopdf during tests: it archives the report
        # HTML, but the archiving and fingerprinting flow is the same.
        stored = base64.b64decode(deca.pdf_attachment_id.datas)
        self.assertLess(len(stored), 5 * 1024 * 1024)
        self.assertEqual(deca.pdf_sha256, hashlib.sha256(stored).hexdigest())
        self.assertTrue(deca.qr_image)

    def test_report_contains_the_mandatory_data(self):
        deca = self._create_deca()
        deca.action_issue()
        html = (
            self.env["ir.actions.report"]
            ._render_qweb_html("l10n_es_deca.action_report_deca", deca.ids)[0]
            .decode()
        )
        self.assertIn(deca.name, html)
        self.assertIn("Contractual shipper", html)
        self.assertIn("Effective carrier", html)
        self.assertIn(self.carrier.name, html)
        self.assertIn("MDP-1234567", html)
        self.assertIn("1234 ABC", html)
        self.assertIn("R 9012 BBB", html)
        self.assertIn(deca.public_url, html)
        self.assertIn("Cement pallet", html)
        self.assertIn("Valencia", html)
        self.assertNotIn("Modification history", html)

    def test_issue_twice_is_blocked(self):
        deca = self._create_deca()
        deca.action_issue()
        with self.assertRaises(UserError):
            deca.action_issue()

    def test_issue_requires_tractor_plate(self):
        deca = self._create_deca(tractor_plate_id=False)
        with self.assertRaises(UserError):
            deca.action_issue()

    def test_an_empty_draft_can_be_saved_and_lists_what_it_needs(self):
        deca = self.env["l10n.es.deca"].create({})
        self.assertEqual(deca.state, "draft")
        self.assertEqual(deca.shipper_id, self.company.partner_id)
        missing = deca.missing_issue_data
        for label in ("Deliveries", "Carrier", "Tractor plate"):
            self.assertIn(label, missing)
        with self.assertRaises(UserError):
            deca.action_issue()

    def test_issue_requires_vat(self):
        self.company.partner_id.vat = False
        deca = self._create_deca()
        with self.assertRaises(UserError):
            deca.action_issue()

    def test_issue_requires_spanish_vat(self):
        # Intra-community VAT valid for base_vat but not Spanish.
        self.company.partner_id.vat = "FR23334175221"
        deca = self._create_deca()
        with self.assertRaises(UserError):
            deca.action_issue()

    def test_carrier_requires_valid_spanish_vat(self):
        with self.assertRaises(ValidationError):
            self.env["res.partner"].create(
                {
                    "name": "Carrier without tax ID",
                    "company_type": "company",
                    "deca_carrier": True,
                }
            )

    def test_verify_integrity(self):
        deca = self._create_deca()
        deca.action_issue()
        deca.action_verify_integrity()
        self.assertIn("Integrity verified", deca.message_ids[0].body)

    def test_verify_integrity_detects_tampering(self):
        deca = self._create_deca()
        deca.action_issue()
        deca.pdf_attachment_id.sudo().write({"datas": base64.b64encode(b"%PDF-fake")})
        deca.action_verify_integrity()
        self.assertIn("does NOT match", deca.message_ids[0].body)

    def test_pickings_frozen_after_issue(self):
        deca = self._create_deca()
        deca.action_issue()
        other = self._create_picking()
        with self.assertRaises(UserError):
            deca.picking_ids = [fields.Command.link(other.id)]

    def test_unlink_only_in_draft(self):
        deca = self._create_deca()
        deca.action_issue()
        with self.assertRaises(UserError):
            deca.unlink()
        draft = self._create_deca()
        self.assertTrue(draft.unlink())

    def test_no_two_active_deca_on_same_picking(self):
        picking = self._create_picking()
        self._create_deca(picking)
        with self.assertRaises(ValidationError):
            self._create_deca(picking)

    def test_incoming_picking_cannot_have_deca(self):
        reception = self._create_picking(picking_type=self.picking_type_in)
        with self.assertRaises(ValidationError):
            self._create_deca(reception)

    def test_plate_must_belong_to_carrier(self):
        with self.assertRaises(ValidationError):
            self._create_deca(tractor_plate_id=self.foreign_tractor.id)

    def test_trailer_plate_type_is_checked(self):
        with self.assertRaises(ValidationError):
            self._create_deca(trailer_plate_id=self.tractor.id)

    def test_service_end_date_after_transport_date(self):
        with self.assertRaises(ValidationError):
            self._create_deca(
                service_end_date=fields.Date.add(self.today, days=-1),
            )

    def test_grouping_requires_same_carrier(self):
        first = self._create_picking()
        second = self._create_picking()
        second.deca_carrier_id = self.other_carrier
        with self.assertRaises(ValidationError):
            self._create_deca(first | second)

    def test_pickings_changed_detected(self):
        deca = self._create_deca()
        deca.action_issue()
        self.assertFalse(deca.pickings_changed)
        deca.picking_ids.move_ids.product_uom_qty = 99
        deca.invalidate_recordset(["pickings_changed"])
        self.assertTrue(deca.pickings_changed)

    def test_cron_closes_public_access(self):
        deca = self._create_deca(
            transport_date=fields.Date.add(self.today, days=-30),
            service_end_date=fields.Date.add(self.today, days=-30),
        )
        deca.action_issue()
        self.assertTrue(deca._is_public_access_open())
        self.env["l10n.es.deca"]._cron_close_public_access()
        self.assertEqual(deca.state, "closed")
        self.assertFalse(deca._is_public_access_open())

    def test_cron_keeps_recent_deca_open(self):
        deca = self._create_deca()
        deca.action_issue()
        self.env["l10n.es.deca"]._cron_close_public_access()
        self.assertEqual(deca.state, "issued")

    def test_issue_email_is_queued(self):
        self.company.partner_id.email = "logistica@empresa.example"
        deca = self._create_deca()
        deca.action_issue()
        mails = self.env["mail.mail"].search([("model", "=", "l10n.es.deca")])
        self.assertTrue(mails)

    def test_vehicle_plate_is_unique_per_carrier(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                self.env["l10n.es.deca.vehicle"].create(
                    {
                        "name": "1234 ABC",
                        "vehicle_type": "tractor",
                        "partner_id": self.carrier.id,
                    }
                )

    def test_vehicle_requires_carrier_partner(self):
        with self.assertRaises(ValidationError):
            self.env["l10n.es.deca.vehicle"].create(
                {
                    "name": "4321 XYZ",
                    "vehicle_type": "tractor",
                    "partner_id": self.customer.id,
                }
            )

    def test_change_history_is_immutable(self):
        deca = self._create_deca()
        deca.action_issue()
        change = self.env["l10n.es.deca.change"].create(
            {
                "deca_id": deca.id,
                "field_label": "Tractor plate",
                "field_name": "tractor_plate_id",
                "old_value": "1234 ABC",
                "new_value": "5678 DEF",
                "reason": "Breakdown",
            }
        )
        with self.assertRaises(UserError):
            change.reason = "Otro"
        with self.assertRaises(UserError):
            change.unlink()

    def test_access_log_purge(self):
        deca = self._create_deca()
        deca.action_issue()
        deca._log_public_access("10.0.0.1", "GET", 200, "curl/8")
        self.assertEqual(len(deca.access_log_ids), 1)
        deca.access_log_ids.flush_recordset()
        self.env.cr.execute(
            "UPDATE l10n_es_deca_access_log SET access_date = "
            "(now() at time zone 'UTC') - interval '400 days' WHERE id = %s",
            (deca.access_log_ids.id,),
        )
        deca.invalidate_recordset(["access_log_ids"])
        self.env["l10n.es.deca.access.log"]._cron_purge_access_logs()
        self.assertFalse(deca.access_log_ids)

    def test_model_fields_have_no_string_context(self):
        """A model-level `context` is sent as a string and breaks web_read.

        Dynamic expressions (`domain`/`context` referencing other fields) must
        be declared on the <field> node of the view.
        """
        for model_name in (
            "l10n.es.deca",
            "l10n.es.deca.line",
            "l10n.es.deca.vehicle",
            "l10n.es.deca.change",
            "l10n.es.deca.access.log",
        ):
            for field in self.env[model_name]._fields.values():
                context = getattr(field, "context", None)
                self.assertNotIsInstance(
                    context,
                    str,
                    f"{model_name}.{field.name} declares a string context",
                )

    def test_list_view_web_search_read(self):
        """The list view must be readable over RPC without a TypeError."""
        deca = self._create_deca()
        model = self.env["l10n.es.deca"]
        views = model.get_views(
            [
                (self.env.ref("l10n_es_deca.view_deca_list").id, "list"),
                (self.env.ref("l10n_es_deca.view_deca_form").id, "form"),
            ]
        )
        spec = {}
        for name in views["models"]["l10n.es.deca"]["fields"]:
            field = model._fields[name]
            if field.type in ("many2one", "many2many", "one2many"):
                spec[name] = {"fields": {"display_name": {}}}
            else:
                spec[name] = {}
        result = model.web_search_read(
            domain=[("id", "=", deca.id)], specification=spec
        )
        self.assertEqual(result["length"], 1)
